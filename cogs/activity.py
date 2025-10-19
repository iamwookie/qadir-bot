import json
import logging
from datetime import datetime

import discord

from config import config
from core import Cog, Qadir
from models.activity import Activity, PartialActivity

GUILD_IDS = config["activity"]["guilds"]
APPLICATIONS = config["activity"]["applications"]

# Atomically pop a field from a Redis hash and return its value
# NOTE: Can be moved to core/scripts.py if needed elsewhere
R_POP_HASH_FIELD = """
    local v = redis.call("HGET", KEYS[1], ARGV[1])
    if v then
        redis.call("HDEL", KEYS[1], ARGV[1])
    end
    return v
"""

logger = logging.getLogger("qadir")


class ActivityCog(Cog, name="Activity", guild_ids=GUILD_IDS):
    """
    A cog to manage executive track user presence activity.
    """

    REDIS_PREFIX: str = "qadir:activity"
    REDIS_LOCK_TTL: int = 5  # seconds

    def _act_to_id(self, activity_name: str) -> str:
        """
        Convert an activity name to its corresponding ID.

        Args:
            activity_name (str): The name of the activity
        Returns:
            str: The corresponding activity ID
        """

        return activity_name.lower().replace(" ", "_")

    def _lock_key(self, action: str, user_id: int, application_id: int) -> str:
        """
        Generate a Redis lock key for activity actions.

        Args:
            action (str): The action being performed (start/stop)
            user_id (int): The user ID
            application_id (int): The application ID

        Returns:
            str: The generated lock key
        """

        return f"{self.REDIS_PREFIX}:lock:{action}:{str(user_id)}:{str(application_id)}"

    async def _pop_user_activity(self, user_id: int, application_id: int) -> PartialActivity | None:
        """
        Pop (atomically) and return a user's tracked activity session data from Redis.

        Args:
            user_id (int): The user ID to get sessions for
            application_id (int): The application ID to pop

        Returns:
            dict: The popped activity session data, or empty dict if none found
        """

        activity_key = f"{self.REDIS_PREFIX}:{str(user_id)}"
        session_data_raw = await self.redis.eval(R_POP_HASH_FIELD, keys=[activity_key], args=[str(application_id)])
        return PartialActivity(**json.loads(session_data_raw)) if session_data_raw else None

    async def _handle_start_activity(self, member: discord.Member, activity: discord.Activity) -> None:
        """
        Handle when a user starts an activity.

        Args:
            member (discord.Member): The member who started the activity
            activity_name (str): The name of the activity started
        """

        app_id = activity.application_id

        if not await self.redis.set(self._lock_key("start", member.id, app_id), 1, nx=True, ex=self.REDIS_LOCK_TTL):
            return  # Another start event is being processed

        start_time: datetime | None = activity.timestamps.get("start") or activity.created_at

        payload = PartialActivity(
            user_id=str(member.id),
            application_id=str(app_id),
            name=activity.name,
            start_time=start_time,
        )
        await self.redis.hsetnx(f"{self.REDIS_PREFIX}:{str(member.id)}", str(app_id), json.dumps(payload.model_dump(), default=str))

        logger.debug(f"[ACTIVITY] Tracked Activity: {member} -> {activity.application_id}")

    async def _handle_stop_activity(self, member: discord.Member, activity: discord.Activity) -> None:
        """
        Handle when a user stops an activity.

        Args:
            member (discord.Member): The member who stopped the activity
            activity_name (str): The name of the activity stopped
        """

        app_id = activity.application_id

        if not await self.redis.set(self._lock_key("stop", member.id, app_id), 1, nx=True, ex=self.REDIS_LOCK_TTL):
            return  # Another stop event is being processed

        tracked = await self._pop_user_activity(member.id, app_id)
        if not tracked:
            return  # Not tracking this activity

        payload = Activity(user_id=str(member.id), application_id=str(app_id), name=tracked.name, start_time=tracked.start_time)
        await payload.insert()

        logger.debug(f"[ACTIVITY] Saved Activity: {member} -> {payload.application_id}")

    @discord.Cog.listener(name="on_presence_update")
    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        """
        Listen for presence updates and print when a user starts an activity.

        Args:
            before: discord.Member: The member before the update
            after: discord.Member: The member after the update
        """

        # Make sure the bot is initialised
        await self.bot.wait_until_initialised()

        # Check if this guild is in our monitored guilds
        if after.guild.id not in GUILD_IDS:
            return

        # Sort activities by application_id for easy comparison
        after_activities: dict[int, discord.Activity] = {
            a.application_id: a for a in after.activities if getattr(a, "application_id", None)
        }
        before_activities: dict[int, discord.Activity] = {
            a.application_id: a for a in before.activities if getattr(a, "application_id", None)
        }

        # Determine started and stopped activities
        started_activities = [after_activities[i] for i in set(after_activities) - set(before_activities)]
        stopped_activities = [before_activities[i] for i in set(before_activities) - set(after_activities)]

        # Process each activity change with deduplication
        for activity in started_activities:
            if activity.application_id in APPLICATIONS:
                try:
                    await self._handle_start_activity(after, activity)
                except Exception:
                    logger.exception("[ACTIVITY] Error Handling Start Activity")

        for activity in stopped_activities:
            if activity.application_id in APPLICATIONS:
                try:
                    await self._handle_stop_activity(after, activity)
                except Exception:
                    logger.exception("[ACTIVITY] Error Handling Stop Activity")


def setup(bot: Qadir) -> None:
    """
    Load the ActivityCog into the bot.

    Args:
        bot (Qadir): The bot instance to load the cog into
    """

    bot.add_cog(ActivityCog(bot))
