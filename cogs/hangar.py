import asyncio
import json
import logging
import math
from datetime import datetime, timezone
from typing import Optional

import aiohttp
import discord
from discord.ext import tasks

from config import config
from core import Cog, Qadir
from core.embeds import ErrorEmbed, HangarEmbed, SuccessEmbed

GUILD_IDS: list[int] = config.get("hangar", {}).get("guilds", [])

logger = logging.getLogger("qadir")


class HangarCog(Cog, name="Hangar", guild_ids=GUILD_IDS):
    """
    A cog to manage executive hangar timers and tracking.
    Used for timing hangar rentals and managing fleet operations.
    """

    def __init__(self, bot: Qadir) -> None:
        super().__init__(bot)

        self.cycle_start: Optional[int] = None

        # Timer phases (in seconds)
        self.RED_PHASE = 2 * 60 * 60  # 2 hours
        self.GREEN_PHASE = 1 * 60 * 60  # 1 hour
        self.BLACK_PHASE = 5 * 60  # 5 minutes
        self.TOTAL_CYCLE = self.RED_PHASE + self.GREEN_PHASE + self.BLACK_PHASE

        # Start background tasks
        self.process_cycle_data.start()
        self.process_hangar_embeds.start()

    def cog_unload(self):
        """Clean up tasks when cog is unloaded."""

        self.process_cycle_data.cancel()
        self.process_hangar_embeds.cancel()

    async def _fetch_cycle_start(self) -> Optional[int]:
        """
        Fetch the cycle start time from contestedzonetimers.com

        Returns:
            Optional[int]: The cycle start time in milliseconds since epoch, or None if fetch failed
        """

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://contestedzonetimers.com/lib/cfg.dat") as response:
                    if response.status == 200:
                        text = await response.text()
                        cycle_start = int(text.strip()) * 1000  # Convert to milliseconds
                        return cycle_start
                    else:
                        logger.error(f"[HANGAR] Failed To Fetch Cycle Start: HTTP {response.status}")
                        return None
        except Exception:
            logger.exception("[HANGAR] Error Fetching Cycle Start")
            return None

    def _calculate_hangar_state(self) -> dict:
        """
        Calculate current hangar state based on cycle timing.

        Returns:
            dict: A dictionary containing hangar state information
        """

        if not self.cycle_start:
            return {
                "status": "Unknown",
                "color": 0x808080,
                "lights": ["⚫"] * 5,
                "time_left": "Unknown",
                "phase_description": "Waiting for cycle data...",
            }

        # Calculate elapsed time and remaining time in current cycle
        elapsed = math.floor((datetime.now().timestamp() * 1000 - self.cycle_start) / 1000)
        remaining = self.TOTAL_CYCLE - (elapsed % self.TOTAL_CYCLE)
        time_left = remaining

        lights = ["⚫"] * 5  # Default to black lights

        # Handle red phase (lights turn green left to right every 24 minutes)
        if time_left > self.GREEN_PHASE + self.BLACK_PHASE:
            red_time = time_left - (self.GREEN_PHASE + self.BLACK_PHASE)
            time_since_red_started = self.RED_PHASE - red_time

            for i in range(5):
                if time_since_red_started >= (i + 1) * 24 * 60:  # Green after its time has passed
                    lights[i] = "🟢"
                else:
                    lights[i] = "🔴"

            return {
                "status": "Hangar Closed",
                "color": 0xFF0000,
                "lights": lights,
                "time_left": self._format_time(red_time),
                "phase_description": f"Opens in `{self._format_time(red_time)}`",
            }

        # Handle green phase (lights turn black left to right every 12 minutes)
        elif time_left > self.BLACK_PHASE:
            green_time = time_left - self.BLACK_PHASE
            time_since_green_started = self.GREEN_PHASE - green_time

            for i in range(5):
                if time_since_green_started >= (i + 1) * 12 * 60:  # Each turns black at 12, 24, 36, 48, 60 min
                    lights[i] = "⚫"
                else:
                    lights[i] = "🟢"

            return {
                "status": "Hangar Open",
                "color": 0x32CD32,
                "lights": lights,
                "time_left": self._format_time(green_time),
                "phase_description": f"Resets in `{self._format_time(green_time)}`",
            }

        # Handle black phase (all lights black for 5 minutes)
        else:
            lights = ["⚫"] * 5
            return {
                "status": "Hangar Resetting",
                "color": 0xFFFF00,
                "lights": lights,
                "time_left": self._format_time(time_left),
                "phase_description": "Hangar is resetting...",
            }

    def _format_time(self, seconds: int) -> str:
        """Format seconds as HH:MM:SS."""

        hours = math.floor(seconds / 3600)
        mins = math.floor((seconds % 3600) / 60)
        secs = seconds % 60

        return f"{hours:02d}:{mins:02d}:{secs:02d}"

    @tasks.loop(hours=24)
    async def process_cycle_data(self):
        """Update cycle start data every day."""

        logger.info("⌛ [HANGAR] Processing Cycle Data...")

        try:
            new_cycle_start = await self._fetch_cycle_start()
            if new_cycle_start:
                self.cycle_start = new_cycle_start
                logger.info(f"⌛ [HANGAR] Processed Cycle Start: {new_cycle_start}")
        except Exception:
            logger.exception("[HANGAR] Error Processing Cycle Data")

    @process_cycle_data.before_loop
    async def before_process_cycle_data(self):
        """Initialize cycle data before starting the loop."""

        await self.bot.wait_until_ready()

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
                    # Remove broken embed from tracking
                    await self.bot.redis.srem("qadir:hangar:embeds", embed_data_str)
        except Exception:
            logger.exception("[HANGAR] Error In process_hangar_embeds")

        logger.debug(f"⌛ [HANGAR] Processed {processed} Hangar Embeds")

    @process_hangar_embeds.before_loop
    async def before_process_hangar_embeds(self):
        """Wait for bot to be ready before starting embed updates."""

        await self.bot.wait_until_ready()

        # Wait for process_cycle_data to fetch initial data
        while not self.cycle_start:
            logger.debug("⌛ [HANGAR] Waiting For Cycle Data...")
            await asyncio.sleep(5)

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

            # Also refresh cycle data
            new_cycle_start = await self._fetch_cycle_start()
            if new_cycle_start:
                self.cycle_start = new_cycle_start

            await ctx.followup.send(
                embed=SuccessEmbed(
                    title="✅ Update Complete", description=f"Successfully updated {embed_count} hangar timer(s) and refreshed cycle data."
                ),
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
