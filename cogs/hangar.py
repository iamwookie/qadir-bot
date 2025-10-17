import json
import logging
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import tasks

from config import config
from core import Cog, Qadir
from models.hangar import HangarEmbedItem
from utils import dt_to_psx
from utils.embeds import ErrorEmbed, HangarEmbed

GUILD_IDS = config["hangar"]["guilds"]

logger = logging.getLogger("qadir")


class HangarCog(Cog, name="Hangar", guild_ids=GUILD_IDS):
    """
    A cog to manage executive hangar timers and tracking.
    """

    _REDIS_PREFIX: str = "qadir:hangar"
    _REDIS_TTL: int = 3600  # seconds

    _OPEN_DURATION: int = 3900385  # milliseconds
    _CLOSE_DURATION: int = 7200711  # milliseconds
    _CYCLE_DURATION: int = _OPEN_DURATION + _CLOSE_DURATION

    # Original Timestamp: 2025-09-21T00:04:27.222-04:00 (EDT, UTC-4)
    _INITIAL_OPEN_TIME: datetime = datetime(2025, 9, 21, 0, 4, 27, 222000, timezone(timedelta(hours=-4))).astimezone(timezone.utc)

    # Define the hangar lights thresholds
    _THRESHOLDS: list[dict] = [
        {"min": 0, "max": 12 * 60 * 1000, "colors": ["green", "green", "green", "green", "green"]},  # Online 5G
        {"min": 12 * 60 * 1000, "max": 24 * 60 * 1000, "colors": ["green", "green", "green", "green", "empty"]},  # Online 4G1E
        {"min": 24 * 60 * 1000, "max": 36 * 60 * 1000, "colors": ["green", "green", "green", "empty", "empty"]},  # Online 3G2E
        {"min": 36 * 60 * 1000, "max": 48 * 60 * 1000, "colors": ["green", "green", "empty", "empty", "empty"]},  # Online 2G3E
        {"min": 48 * 60 * 1000, "max": 60 * 60 * 1000, "colors": ["green", "empty", "empty", "empty", "empty"]},  # Online 1G4E
        {"min": 60 * 60 * 1000, "max": 65 * 60 * 1000, "colors": ["empty", "empty", "empty", "empty", "empty"]},  # Online 5E
        {"min": 65 * 60 * 1000, "max": 89 * 60 * 1000, "colors": ["red", "red", "red", "red", "red"]},  # Offline 5R
        {"min": 89 * 60 * 1000, "max": 113 * 60 * 1000, "colors": ["green", "red", "red", "red", "red"]},  # Offline 1G4R
        {"min": 113 * 60 * 1000, "max": 137 * 60 * 1000, "colors": ["green", "green", "red", "red", "red"]},  # Offline 2G3R
        {"min": 137 * 60 * 1000, "max": 161 * 60 * 1000, "colors": ["green", "green", "green", "red", "red"]},  # Offline 3G2R
        {"min": 161 * 60 * 1000, "max": 185 * 60 * 1000, "colors": ["green", "green", "green", "green", "red"]},  # Offline 4G1R
    ]

    def __init__(self, bot: Qadir) -> None:
        super().__init__(bot)

        # Start cog tasks
        # self.process_hangar_embeds.start()

    def cog_unload(self):
        """Clean up tasks when cog is unloaded."""

        self._process_hangar_embeds.cancel()

    def _get_next_status_change(self, current_time: datetime) -> dict:
        """
        Get the next status change information based on the timing system.

        Args:
            current_time (datetime): The current UTC time

        Returns:
            dict: A dictionary containing the next status change information
        """

        elapsed_time_since_initial_open = current_time - self._INITIAL_OPEN_TIME
        elapsed_ms = elapsed_time_since_initial_open.total_seconds() * 1000
        time_in_current_cycle = elapsed_ms % self._CYCLE_DURATION

        if time_in_current_cycle < self._OPEN_DURATION:
            # Hangars are online
            next_status_change = current_time + timedelta(milliseconds=(self._OPEN_DURATION - time_in_current_cycle))
            return {"status": "ONLINE", "next_status_change": next_status_change}
        else:
            # Hangars are offline
            remaining_close_duration = time_in_current_cycle - self._OPEN_DURATION
            next_status_change = current_time + timedelta(milliseconds=(self._CLOSE_DURATION - remaining_close_duration))
            return {"status": "OFFLINE", "next_status_change": next_status_change}

    def _get_next_light_change(self, current_time: datetime, time_in_cycle: float) -> datetime:
        """
        Calculate the next light change time based on the current position in the cycle.

        Args:
            current_time (datetime): Current UTC time
            time_in_cycle (float): Current position in cycle (milliseconds)

        Returns:
            datetime: The next light change time
        """

        # Find which threshold we're in
        current_threshold_index = None
        for i, threshold in enumerate(self._THRESHOLDS):
            if time_in_cycle >= threshold["min"] and time_in_cycle < threshold["max"]:
                current_threshold_index = i
                break

        # If no threshold found, we're beyond the defined ranges (last threshold)
        if current_threshold_index is None:
            current_threshold_index = len(self._THRESHOLDS) - 1

        # Calculate next light change time
        if current_threshold_index < len(self._THRESHOLDS) - 1:
            # Next change is at the end of current threshold (start of next threshold)
            current_threshold = self._THRESHOLDS[current_threshold_index]
            time_until_next_change_ms: float = (current_threshold["max"] - time_in_cycle) + 1000
            return current_time + timedelta(milliseconds=time_until_next_change_ms)
        else:
            # We're in the last threshold, next change is start of next cycle
            time_until_next_cycle_ms: float = (self._CYCLE_DURATION - time_in_cycle) + 1000
            return current_time + timedelta(milliseconds=time_until_next_cycle_ms)

    def _calculate_hangar_state(self) -> dict:
        """
        Calculate current hangar state based on the new exec.xyxll.com timing system.

        Returns:
            dict: A dictionary containing hangar state information
        """

        current_time = discord.utils.utcnow()
        status_info = self._get_next_status_change(current_time)

        # Calculate time in current cycle
        elapsed_time_since_initial_open = current_time - self._INITIAL_OPEN_TIME
        elapsed_ms = elapsed_time_since_initial_open.total_seconds() * 1000
        time_in_cycle = elapsed_ms % self._CYCLE_DURATION

        # Find which threshold we're in
        current_threshold = None
        for threshold in self._THRESHOLDS:
            if time_in_cycle >= threshold["min"] and time_in_cycle < threshold["max"]:
                current_threshold = threshold
                break

        # If no threshold found, we're beyond the defined ranges
        if not current_threshold:
            # This handles the case where time_in_cycle >= 185*60*1000 (11100000ms)
            # Use the last threshold to maintain the current state during the gap
            current_threshold = self._THRESHOLDS[-1]

        # Convert colors to emojis
        lights = []
        for color in current_threshold["colors"]:
            if color == "green":
                lights.append("🟢")
            elif color == "red":
                lights.append("🔴")
            else:  # empty
                lights.append("⚫")

        # Determine status and color based on online/offline
        if status_info["status"] == "ONLINE":
            status = "Hangar Open"
            color = 0x32CD32  # Green
        else:
            status = "Hangar Closed"
            color = 0xFF0000  # Red

        next_status_change: datetime = status_info["next_status_change"]
        next_light_change = self._get_next_light_change(current_time, time_in_cycle)

        return {
            "status": status,
            "color": color,
            "lights": lights,
            "next_status_change": next_status_change,
            "next_light_change": next_light_change,
        }

    async def _get_or_fetch_hangar_data(self) -> list[HangarEmbedItem] | None:
        """
        Retrieve a list of all hangar embed data.

        Args:
            message_id (int): The message ID of the hangar

        Returns:
            list[HangarEmbedItem] | None: A list of HangarEmbedItem, or None
        """

        try:
            cached = await self.redis.get(f"{self._REDIS_PREFIX}:embeds")
            if cached:
                return [HangarEmbedItem(**json.loads(item)) for item in json.loads(cached)]

            items = await HangarEmbedItem.find_all().to_list()
            if items:
                # Cache the data in Redis for future use
                await self.redis.set(
                    f"{self._REDIS_PREFIX}:embeds",
                    json.dumps([item.model_dump() for item in items], default=str),
                    ex=self._REDIS_TTL,
                )
                return items

            return None
        except Exception:
            logger.exception("[HANGAR] Error Fetching Hangar Embed Data")
            return None

    @tasks.loop(minutes=1)
    async def _process_hangar_embeds(self):
        """Update all tracked hangar embeds dynamically or every minute."""

        logger.debug("⌛ [HANGAR] Processing Hangar Embeds...")

        # Get all tracked embed message IDs
        embed_items = await HangarEmbedItem.find_all().to_list()
        if not embed_items:
            logger.debug("⌛ [HANGAR] No Hangar Embeds To Process")
            return

        # Calculate current state and create the HangarEmbed
        state = self._calculate_hangar_state()
        embed = HangarEmbed(state)
        processed = 0

        # Update each tracked embed
        for embed_item in embed_items:
            try:
                channel_id = int(embed_item.channel_id)
                message_id = int(embed_item.message_id)

                message = await self.bot.get_message(message_id)
                if not message:
                    channel = await self.bot.get_channel(channel_id)
                    if not channel:
                        channel = await self.bot.fetch_channel(channel_id)

                    message = await channel.fetch_message(message_id)

                await message.edit(embed=embed)

                processed += 1
            except discord.NotFound:
                logger.warning(f"⌛ [HANGAR] Hangar Embed Not Found: {embed_item.message_id}")
                # Remove the missing embed from tracking
                await embed_item.delete()
            except Exception:
                logger.exception(f"⌛ [HANGAR] Error Processing Hangar Embed: {embed_item.message_id}")

        next_light_change: datetime = state["next_light_change"]

        # Update task interval to run at the next light change time
        self._process_hangar_embeds.change_interval(time=[next_light_change.time()])
        logger.debug(f"⌛ [HANGAR] Processing Hangar Embeds Rescheduled To: {dt_to_psx(next_light_change)}")
        logger.debug(f"⌛ [HANGAR] Processed {processed} Hangar Embeds")

    @_process_hangar_embeds.before_loop
    async def before_process_hangar_embeds(self):
        """Wait for bot to be initialised before processing hangar embeds."""

        await self.bot.wait_until_initialised()

    @_process_hangar_embeds.error
    async def process_hangar_embeds_error(self, error: Exception):
        """
        Handle errors in the process_hangar_embeds loop.

        Args:
            error (Exception): The raised exception
        """

        logger.error("⌛ [HANGAR] Error Processing Hangar Embeds", exc_info=error)

    # Hangar command group
    hangar = discord.SlashCommandGroup("hangar", "Manage executive hangar operations")

    @hangar.command(description="Create an embed to track the executive hangar status")
    async def create(self, ctx: discord.ApplicationContext) -> None:
        """
        Send an embed that displays the current hangar status with a live updating timer.

        Args:
            ctx (discord.ApplicationContext): The application context
        """

        await ctx.defer()

        # Calculate current state
        state = self._calculate_hangar_state()
        embed = HangarEmbed(state)

        # Send the embed
        try:
            message: discord.Message = await ctx.channel.send(embed=embed)
        except Exception:
            logger.exception("[HANGAR] Error Sending Hangar Embed")
            embed = ErrorEmbed(description="Failed to create the hangar embed. Are you sure I have permissions?")
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        # Track this embed for updates
        try:
            embed_item = HangarEmbedItem(
                message_id=str(message.id),
                channel_id=str(ctx.channel.id),
                guild_id=str(ctx.guild.id),
            )
            await embed_item.insert()

            # Invalidate the cache
            await self.redis.delete(f"{self._REDIS_PREFIX}:embeds")
        except Exception:
            logger.exception("[HANGAR] Error Saving HangarEmbedItem")
            embed = ErrorEmbed(description="Failed to create the hangar embed. Please try again.")
            await ctx.followup.send(embed=embed, ephemeral=True)
            await message.delete()
            return

        logger.debug(f"[HANGAR] Created Hangar Timer Embed {message.id} In Channel {ctx.channel.id}")


def setup(bot: Qadir) -> None:
    """
    Load the HangarCog into the bot.

    Args:
        bot (Qadir): The bot instance to load the cog into
    """

    bot.add_cog(HangarCog(bot))
