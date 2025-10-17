import json
import logging

import discord

from config import config
from core import Cog, Qadir
from models.activities import Activity, PartialActivity

GUILD_IDS = config["activities"]["guilds"]

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


class ActivitiesCog(Cog, name="Activities", guild_ids=GUILD_IDS):
    """
    A cog to manage executive track user presence activity.
    """

    REDIS_PREFIX: str = "qadir:activities"
    REDIS_LOCK_TTL: int = 3  # seconds

    _ACTIVITIES: list[str] = ["star_citizen", "spotify"]

    def init__(self, bot: Qadir) -> None:
        """
        Initialize the cog.

        Args:
            bot (Qadir): The bot instance to load the cog into
        """

        super().__init__(bot)

    def _act_to_id(self, activity_name: str) -> str:
        """
        Convert an activity name to its corresponding ID.

        Args:
            activity_name (str): The name of the activity
        Returns:
            str: The corresponding activity ID
        """

        return activity_name.lower().replace(" ", "_")

    async def _pop_user_activity(self, user_id: int, activity_id: str) -> PartialActivity | None:
        """
        Pop (atomically) and return a user's tracked activity session data from Redis.

        Args:
            user_id (int): The user ID to get sessions for
            activity_id (str): The activity ID to pop

        Returns:
            dict: The popped activity session data, or empty dict if none found
        """

        activity_key = f"{self.REDIS_PREFIX}:{str(user_id)}"
        session_data_raw = await self.redis.eval(R_POP_HASH_FIELD, keys=[activity_key], args=[activity_id])
        return PartialActivity(**json.loads(session_data_raw)) if session_data_raw else None

    async def _handle_start_activity(self, member: discord.Member, activity_name: str) -> None:
        """
        Handle when a user starts an activity.

        Args:
            member (discord.Member): The member who started the activity
            activity_name (str): The name of the activity started
        """

        activity_id = self._act_to_id(activity_name)
        activity_data = PartialActivity(user_id=str(member.id), activity=activity_id)
        await self.redis.hsetnx(f"{self.REDIS_PREFIX}:{str(member.id)}", activity_id, json.dumps(activity_data.model_dump(), default=str))
        logger.debug(f"[ACTIVITIES] Tracked Activity: {member} -> {activity_id}")

    async def _handle_stop_activity(self, member: discord.Member, activity_name: str) -> None:
        """
        Handle when a user stops an activity.

        Args:
            member (discord.Member): The member who stopped the activity
            activity_name (str): The name of the activity stopped
        """

        activity_id = self._act_to_id(activity_name)
        tracked = await self._pop_user_activity(member.id, activity_id)
        if not tracked:
            return  # Not tracking this activity

        activity = Activity(user_id=str(member.id), activity=tracked.activity, start_time=tracked.start_time)
        await activity.insert()

        logger.debug(f"[ACTIVITIES] Saved Activity: {member} -> {activity.activity}")

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

        # Get activities before and after
        after_activities: set[str] = set()
        before_activities: set[str] = set()

        if after.activities:
            after_activities = {activity.name for activity in after.activities if hasattr(activity, "name")}

        if before.activities:
            before_activities = {activity.name for activity in before.activities if hasattr(activity, "name")}

        started_activities = after_activities - before_activities
        stopped_activities = before_activities - after_activities

        # Process each activity change with deduplication
        for activity_name in started_activities:
            if self._act_to_id(activity_name) in self._ACTIVITIES:
                lock_key = f"{self.REDIS_PREFIX}:lock:start:{str(after.id)}:{self._act_to_id(activity_name)}"
                if await self.redis.set(lock_key, 1, nx=True, ex=self.REDIS_LOCK_TTL):
                    try:
                        await self._handle_start_activity(after, activity_name)
                    except Exception:
                        logger.exception("[ACTIVITIES] Error Handling Start Activity")

        for activity_name in stopped_activities:
            if self._act_to_id(activity_name) in self._ACTIVITIES:
                lock_key = f"{self.REDIS_PREFIX}:lock:stop:{str(after.id)}:{self._act_to_id(activity_name)}"
                if await self.redis.set(lock_key, 1, nx=True, ex=self.REDIS_LOCK_TTL):
                    try:
                        await self._handle_stop_activity(after, activity_name)
                    except Exception:
                        logger.exception("[ACTIVITIES] Error Handling Stop Activity")


def setup(bot: Qadir) -> None:
    """
    Load the ActivitiesCog into the bot.

    Args:
        bot (Qadir): The bot instance to load the cog into
    """

    bot.add_cog(ActivitiesCog(bot))
