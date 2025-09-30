import json
import logging
import math
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import tasks

from config import config
from core import Cog, Qadir
from core.embeds import ErrorEmbed, HangarEmbed, SuccessEmbed

GUILD_IDS: list[int] = config["hangar"]["guilds"]

logger = logging.getLogger("qadir")


class HangarCog(Cog, name="Hangar", guild_ids=GUILD_IDS):
    """
    A cog to manage executive hangar timers and tracking.
    Used for timing hangar rentals and managing fleet operations.
    """

    def __init__(self, bot: Qadir) -> None:
        super().__init__(bot)

        # New timing constants from exec.xyxll.com
        self.OPEN_DURATION = 3900375  # milliseconds
        self.CLOSE_DURATION = 7200692  # milliseconds
        self.CYCLE_DURATION = self.OPEN_DURATION + self.CLOSE_DURATION

        # Original Timestamp: 2025-09-21T00:04:27.222-04:00 (EDT, UTC-4)
        eastern_tz = timezone(timedelta(hours=-4))
        initial_time_edt = datetime(2025, 9, 21, 0, 4, 27, 222000, eastern_tz)
        self.INITIAL_OPEN_TIME = initial_time_edt.astimezone(timezone.utc)

        # Start background tasks
        self.process_hangar_embeds.start()

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
            next_change_time = current_time + timedelta(milliseconds=(self.OPEN_DURATION - time_in_current_cycle))
            return {"status": "ONLINE", "next_change_time": next_change_time}
        else:
            # Hangars are offline
            remaining_close_duration = time_in_current_cycle - self.OPEN_DURATION
            next_change_time = current_time + timedelta(milliseconds=(self.CLOSE_DURATION - remaining_close_duration))
            return {"status": "OFFLINE", "next_change_time": next_change_time}

    def _calculate_hangar_state(self) -> dict:
        """
        Calculate current hangar state based on the new exec.xyxll.com timing system.

        Returns:
            dict: A dictionary containing hangar state information
        """

        current_time = datetime.now(timezone.utc)
        status_info = self._get_next_status_change(current_time)

        # Calculate time in current cycle
        elapsed_time_since_initial_open = current_time - self.INITIAL_OPEN_TIME
        elapsed_ms = elapsed_time_since_initial_open.total_seconds() * 1000
        time_in_cycle = elapsed_ms % self.CYCLE_DURATION

        # Define the thresholds
        thresholds = [
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

        # Find which threshold we're in
        current_threshold = None
        for threshold in thresholds:
            if time_in_cycle >= threshold["min"] and time_in_cycle < threshold["max"]:
                current_threshold = threshold
                break

        # If no threshold found, we're beyond the defined ranges
        if not current_threshold:
            # This handles the case where time_in_cycle >= 185*60*1000 (11100000ms)
            # The cycle is 11101067ms, so we need to handle the last 1067ms
            # Use the last threshold pattern (4G1R) for the remainder
            current_threshold = thresholds[-1]

        # Convert colors to emoji exactly as in the original
        lights = []
        for color in current_threshold["colors"]:
            if color == "green":
                lights.append("🟢")
            elif color == "red":
                lights.append("🔴")
            else:  # empty
                lights.append("⚫")

        # Calculate time remaining until next change
        time_remaining: timedelta = status_info["next_change_time"] - current_time
        remaining_seconds = int(time_remaining.total_seconds())

        # Determine status and color based on online/offline
        if status_info["status"] == "ONLINE":
            status = "Hangar Open"
            color = 0x32CD32  # Green
        else:
            status = "Hangar Closed"
            color = 0xFF0000  # Red

        return {
            "status": status,
            "color": color,
            "lights": lights,
            "time_left": self._format_time(remaining_seconds),
        }

    def _format_time(self, seconds: int) -> str:
        """Format seconds as HH:MM:SS."""

        hours = math.floor(seconds / 3600)
        mins = math.floor((seconds % 3600) / 60)
        secs = seconds % 60

        return f"{hours:02d}:{mins:02d}:{secs:02d}"

    @tasks.loop(minutes=1)
    async def process_hangar_embeds(self):
        """Update all tracked hangar embeds every minute."""

        logger.debug("⌛ [HANGAR] Processing Hangar Embeds...")

        try:
            # Get all tracked embed message IDs
            embed_ids = await self.bot.redis.smembers("qadir:hangar:embeds")

            if not embed_ids:
                logger.debug("⌛ [HANGAR] No Hangar Embeds To Process")
                return

            # Calculate current state
            state = self._calculate_hangar_state()
            embed = HangarEmbed(state)
            processed = 0

            # Update each tracked embed
            for embed_data_str in embed_ids:
                try:
                    embed_data = json.loads(embed_data_str)
                    channel_id = embed_data["channel_id"]
                    message_id = embed_data["message_id"]

                    # Get channel and message
                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        channel = await self.bot.fetch_channel(channel_id)

                    message = await channel.fetch_message(message_id)
                    await message.edit(embed=embed)

                    processed += 1

                except Exception:
                    logger.exception(f"[HANGAR] Failed To Process Embed: {embed_data_str}")
                    # NOTE: Disabled for now. Remove broken embed from tracking
                    # await self.bot.redis.srem("qadir:hangar:embeds", embed_data_str)
        except Exception:
            logger.exception("[HANGAR] Error In process_hangar_embeds")

        logger.debug(f"⌛ [HANGAR] Processed {processed} Hangar Embeds")

    @process_hangar_embeds.before_loop
    async def before_process_hangar_embeds(self):
        """Wait for bot to be ready before starting embed updates."""

        await self.bot.wait_until_ready()

    # Hangar command group
    hangar = discord.SlashCommandGroup("hangar", "Manage executive hangar operations")

    @hangar.command(description="Create a hangar status embed with a live timer that auto-updates")
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
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            await self.bot.redis.sadd("qadir:hangar:embeds", json.dumps(embed_data))
            logger.info(f"[HANGAR] Created Hangar Timer Embed {message.id} in Channel {ctx.channel.id}")
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
            embed_ids = await self.bot.redis.smembers("qadir:hangar:embeds")
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

    :param bot: The Qadir instance
    """

    bot.add_cog(HangarCog(bot))
