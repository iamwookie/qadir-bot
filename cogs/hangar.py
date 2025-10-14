import json
import logging
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import tasks

from config import config
from core import Cog, Qadir
from utils import dt_to_psx
from utils.embeds import ErrorEmbed, HangarEmbed, SuccessEmbed

GUILD_IDS = config["hangar"]["guilds"]

logger = logging.getLogger("qadir")


class HangarCog(Cog, name="Hangar", guild_ids=GUILD_IDS):
    """
    A cog to manage executive hangar timers and tracking.
    """

    REDIS_PREFIX: str = "qadir:hangar"

    # Define the hangar lights thresholds
    THRESHOLDS: list[dict] = [
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

        # Timing constants from exec.xyxll.com
        self.OPEN_DURATION = 3900385  # milliseconds
        self.CLOSE_DURATION = 7200711  # milliseconds
        self.CYCLE_DURATION = self.OPEN_DURATION + self.CLOSE_DURATION

        # Original Timestamp: 2025-09-21T00:04:27.222-04:00 (EDT, UTC-4)
        eastern_tz = timezone(timedelta(hours=-4))
        initial_time_edt = datetime(2025, 9, 21, 0, 4, 27, 222000, eastern_tz)
        self.INITIAL_OPEN_TIME = initial_time_edt.astimezone(timezone.utc)

        # Start cog tasks
        # self.process_hangar_embeds.start()

    def cog_unload(self):
        """Clean up tasks when cog is unloaded."""

        self.process_hangar_embeds.cancel()

    def _get_next_status_change(self, current_time: datetime) -> dict:
        """
        Get the next status change information based on the timing system.

        Args:
            current_time (datetime): The current UTC time

        Returns:
            dict: A dictionary containing the next status change information
        """

        elapsed_time_since_initial_open = current_time - self.INITIAL_OPEN_TIME
        elapsed_ms = elapsed_time_since_initial_open.total_seconds() * 1000
        time_in_current_cycle = elapsed_ms % self.CYCLE_DURATION

        if time_in_current_cycle < self.OPEN_DURATION:
            # Hangars are online
            next_status_change = current_time + timedelta(milliseconds=(self.OPEN_DURATION - time_in_current_cycle))
            return {"status": "ONLINE", "next_status_change": next_status_change}
        else:
            # Hangars are offline
            remaining_close_duration = time_in_current_cycle - self.OPEN_DURATION
            next_status_change = current_time + timedelta(milliseconds=(self.CLOSE_DURATION - remaining_close_duration))
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
        for i, threshold in enumerate(self.THRESHOLDS):
            if time_in_cycle >= threshold["min"] and time_in_cycle < threshold["max"]:
                current_threshold_index = i
                break

        # If no threshold found, we're beyond the defined ranges (last threshold)
        if current_threshold_index is None:
            current_threshold_index = len(self.THRESHOLDS) - 1

        # Calculate next light change time
        if current_threshold_index < len(self.THRESHOLDS) - 1:
            # Next change is at the end of current threshold (start of next threshold)
            current_threshold = self.THRESHOLDS[current_threshold_index]
            time_until_next_change_ms: float = (current_threshold["max"] - time_in_cycle) + 1000
            return current_time + timedelta(milliseconds=time_until_next_change_ms)
        else:
            # We're in the last threshold, next change is start of next cycle
            time_until_next_cycle_ms: float = (self.CYCLE_DURATION - time_in_cycle) + 1000
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
        elapsed_time_since_initial_open = current_time - self.INITIAL_OPEN_TIME
        elapsed_ms = elapsed_time_since_initial_open.total_seconds() * 1000
        time_in_cycle = elapsed_ms % self.CYCLE_DURATION

        # Find which threshold we're in
        current_threshold = None
        for threshold in self.THRESHOLDS:
            if time_in_cycle >= threshold["min"] and time_in_cycle < threshold["max"]:
                current_threshold = threshold
                break

        # If no threshold found, we're beyond the defined ranges
        if not current_threshold:
            # This handles the case where time_in_cycle >= 185*60*1000 (11100000ms)
            # Use the last threshold to maintain the current state during the gap
            current_threshold = self.THRESHOLDS[-1]

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
        next_light_change: datetime = self._get_next_light_change(current_time, time_in_cycle)

        return {
            "status": status,
            "color": color,
            "lights": lights,
            "next_status_change": next_status_change,
            "next_light_change": next_light_change,
        }

    @tasks.loop(minutes=1)
    async def process_hangar_embeds(self):
        """Update all tracked hangar embeds dynamically or every minute."""

        logger.debug("⌛ [HANGAR] Processing Hangar Embeds...")

        # Get all tracked embed message IDs
        embed_ids = await self.redis.smembers(f"{self.REDIS_PREFIX}:embeds")

        if not embed_ids:
            logger.debug("⌛ [HANGAR] No Hangar Embeds To Process")
            return

        # Calculate current state and create the HangarEmbed
        state = self._calculate_hangar_state()
        embed = HangarEmbed(state)
        processed = 0

        # Update each tracked embed
        for embed_data_raw in embed_ids:
            try:
                embed_data = json.loads(embed_data_raw)
                channel_id = embed_data["channel_id"]
                message_id = embed_data["message_id"]

                # Get channel and message
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    channel = await self.bot.fetch_channel(channel_id)

                message = await channel.fetch_message(message_id)
                await message.edit(embed=embed)

                processed += 1
            except discord.NotFound:
                logger.warning(f"⌛ [HANGAR] Hangar Embed Not Found: {embed_data_raw}")
                # Remove the missing embed from tracking
                await self.redis.srem("self.REDIS_PREFIX:embeds", embed_data_raw)
            except Exception:
                logger.exception(f"⌛ [HANGAR] Error Processing Hangar Embed: {embed_data_raw}")

        next_light_change: datetime = state["next_light_change"]

        # Update task interval to run at the next light change time
        self.process_hangar_embeds.change_interval(time=[next_light_change.time()])
        logger.debug(f"⌛ [HANGAR] Processing Hangar Embeds Rescheduled To: {dt_to_psx(next_light_change)}")
        logger.debug(f"⌛ [HANGAR] Processed {processed} Hangar Embeds")

    @process_hangar_embeds.before_loop
    async def before_process_hangar_embeds(self):
        """Wait for bot to be ready before processing hangar embeds."""

        await self.bot.wait_until_ready()

    @process_hangar_embeds.error
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
    async def show(self, ctx: discord.ApplicationContext) -> None:
        """
        Send an embed that displays the current hangar status with a live updating timer.

        Args:
            ctx (discord.ApplicationContext): The application context
        """

        await ctx.defer()

        try:
            # Calculate current state
            state = self._calculate_hangar_state()
            embed = HangarEmbed(state)

            # Send the embed
            message = await ctx.followup.send(embed=embed)

            # Track this embed for updates
            embed_data = {
                "channel_id": ctx.channel.id,
                "message_id": message.id,
                "created_by": ctx.author.id,
                "created_at": dt_to_psx(discord.utils.utcnow()),
            }

            await self.redis.sadd("self.REDIS_PREFIX:embeds", json.dumps(embed_data))
            logger.debug(f"[HANGAR] Created Hangar Timer Embed {message.id} In Channel {ctx.channel.id}")
        except Exception:
            logger.exception("[HANGAR] Error Creating Hangar Embed")
            await ctx.followup.send(embed=ErrorEmbed(description="Failed to create hangar timer. Please try again."), ephemeral=True)

    @hangar.command(description="Manually refresh the cycle data")
    async def update(self, ctx: discord.ApplicationContext) -> None:
        """
        Manually trigger a refresh of the cycle data of all hangar status embeds.

        Args:
            ctx (discord.ApplicationContext): The application context
        """

        await ctx.defer(ephemeral=True)

        try:
            # Get tracked embeds count
            embed_ids = await self.redis.smembers("self.REDIS_PREFIX:embeds")
            embed_count = len(embed_ids)

            if embed_count == 0:
                await ctx.followup.send(embed=ErrorEmbed(description="No hangar timers are currently being tracked."), ephemeral=True)
                return

            # Manually trigger the update task
            await self.process_hangar_embeds()

            await ctx.followup.send(
                embed=SuccessEmbed(title="✅ Update Complete", description=f"Successfully updated {embed_count} hangar timer(s)."),
                ephemeral=True,
            )

        except Exception:
            logger.exception("[HANGAR] Error In Manual Update")
            await ctx.followup.send(embed=ErrorEmbed(description="Failed to update hangar timers. Please try again."), ephemeral=True)


def setup(bot: Qadir) -> None:
    """
    Load the HangarCog into the bot.

    Args:
        bot (Qadir): The bot instance to load the cog into
    """

    bot.add_cog(HangarCog(bot))
