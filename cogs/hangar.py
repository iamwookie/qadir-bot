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
from core.embeds import ErrorEmbed, SuccessEmbed

GUILD_IDS: list[int] = config.get("hangar", {}).get("guilds", [])

logger = logging.getLogger("qadir")


class HangarCog(Cog, name="Hangar", guild_ids=GUILD_IDS):
    """
    A cog to manage Star Citizen executive hangar timers and tracking.
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
        self.update_cycle_data.start()
        self.update_hangar_embeds.start()

    def cog_unload(self):
        """Clean up tasks when cog is unloaded."""
        self.update_cycle_data.cancel()
        self.update_hangar_embeds.cancel()

    async def _fetch_cycle_start(self) -> Optional[int]:
        """Fetch the cycle start time from contestedzonetimers.com"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://contestedzonetimers.com/lib/cfg.dat") as response:
                    if response.status == 200:
                        text = await response.text()
                        cycle_start = int(text.strip()) * 1000  # Convert to milliseconds
                        logger.info(f"[HANGAR] Fetched cycle start: {cycle_start}")
                        return cycle_start
                    else:
                        logger.error(f"[HANGAR] Failed to fetch cfg.dat: HTTP {response.status}")
                        return None
        except Exception as e:
            logger.error(f"[HANGAR] Error fetching cycle start: {e}")
            return None

    def _calculate_hangar_state(self) -> dict:
        """Calculate current hangar state based on cycle timing."""
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
                "phase_description": f"Opens in {self._format_time(red_time)}",
                "mini_timer": f"Opens in {self._format_time(red_time)}",
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
                "phase_description": f"Resets in {self._format_time(green_time)}",
                "mini_timer": f"Resets in {self._format_time(green_time)}",
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
                "mini_timer": "",
            }

    def _format_time(self, seconds: int) -> str:
        """Format seconds as HH:MM:SS."""

        hours = math.floor(seconds / 3600)
        mins = math.floor((seconds % 3600) / 60)
        secs = seconds % 60

        return f"{hours:02d}:{mins:02d}:{secs:02d}"

    def _create_hangar_embed(self, state: dict) -> discord.Embed:
        """Create the hangar status embed."""

        embed = discord.Embed(title="🚀 Star Citizen Executive Hangar Status", color=state["color"], timestamp=datetime.now(timezone.utc))

        # Status field
        embed.add_field(name="🎯 Current Status", value=f"**{state['status']}**", inline=True)

        # Timer field
        embed.add_field(name="⏰ Time Remaining", value=f"`{state['time_left']}`", inline=True)

        # Phase description
        embed.add_field(name="📋 Phase Info", value=state["phase_description"], inline=True)

        # Light status (visual indicator)
        lights_display = " ".join(state["lights"])
        embed.add_field(name="💡 Hangar Lights", value=lights_display, inline=False)

        # Add explanation
        if state["status"] == "Hangar Closed":
            embed.add_field(name="ℹ️ Red Phase", value="Lights turn green every 24 minutes as hangar opening approaches.", inline=False)
        elif state["status"] == "Hangar Open":
            embed.add_field(name="ℹ️ Green Phase", value="Lights turn black every 12 minutes as reset approaches.", inline=False)
        elif state["status"] == "Hangar Resetting":
            embed.add_field(name="ℹ️ Black Phase", value="All systems resetting. Hangar will reopen soon.", inline=False)

        embed.set_footer(text="Data from contestedzonetimers.com")
        return embed

    @tasks.loop(days=1)
    async def update_cycle_data(self):
        """Update cycle start data every day."""

        try:
            new_cycle_start = await self._fetch_cycle_start()
            if new_cycle_start:
                self.cycle_start = new_cycle_start
                # Store in Redis for persistence
                await self.bot.redis.set("qadir:hangar:cycle_start", str(new_cycle_start))
                logger.info(f"[HANGAR] Updated cycle start: {new_cycle_start}")
        except Exception as e:
            logger.error(f"[HANGAR] Error updating cycle data: {e}")

    @update_cycle_data.before_loop
    async def before_update_cycle_data(self):
        """Initialize cycle data before starting the loop."""

        await self.bot.wait_until_ready()

        # Try to load from Redis first
        try:
            stored_cycle_start = await self.bot.redis.get("qadir:hangar:cycle_start")
            if stored_cycle_start:
                self.cycle_start = int(stored_cycle_start)
                logger.info(f"[HANGAR] Loaded cycle start from Redis: {self.cycle_start}")
            else:
                # Fetch fresh data
                self.cycle_start = await self._fetch_cycle_start()
                if self.cycle_start:
                    await self.bot.redis.set("qadir:hangar:cycle_start", str(self.cycle_start))
        except Exception as e:
            logger.error(f"[HANGAR] Error initializing cycle data: {e}")

    @tasks.loop(minutes=1)
    async def update_hangar_embeds(self):
        """Update all tracked hangar embeds every minute."""

        try:
            # Get all tracked embed message IDs
            embed_ids = await self.bot.redis.smembers("qadir:hangar:embeds")

            if not embed_ids:
                return

            # Calculate current state
            state = self._calculate_hangar_state()
            embed = self._create_hangar_embed(state)

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

                except Exception as e:
                    logger.error(f"[HANGAR] Failed to update embed {embed_data_str}: {e}")
                    # Remove broken embed from tracking
                    await self.bot.redis.srem("qadir:hangar:embeds", embed_data_str)

        except Exception as e:
            logger.error(f"[HANGAR] Error in update_hangar_embeds: {e}")

    @update_hangar_embeds.before_loop
    async def before_update_hangar_embeds(self):
        """Wait for bot to be ready before starting embed updates."""
        await self.bot.wait_until_ready()

    # Hangar command group
    hangar = discord.SlashCommandGroup("hangar", "Manage Star Citizen executive hangar operations")

    @hangar.command(description="Show current executive hangar status with live timer")
    async def show(self, ctx: discord.ApplicationContext) -> None:
        """Display the current hangar status with a live updating timer."""
        await ctx.defer()

        try:
            # Calculate current state
            state = self._calculate_hangar_state()
            embed = self._create_hangar_embed(state)

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
            logger.info(f"[HANGAR] Created hangar timer embed {message.id} in channel {ctx.channel.id}")

        except Exception as e:
            logger.error(f"[HANGAR] Error creating hangar embed: {e}")
            await ctx.followup.send(embed=ErrorEmbed(description="Failed to create hangar timer. Please try again."), ephemeral=True)

    @hangar.command(description="Manually update hangar status embeds")
    async def update(self, ctx: discord.ApplicationContext) -> None:
        """Manually trigger an update of all hangar status embeds."""
        await ctx.defer(ephemeral=True)

        try:
            # Get tracked embeds count
            embed_ids = await self.bot.redis.smembers("qadir:hangar:embeds")
            embed_count = len(embed_ids)

            if embed_count == 0:
                await ctx.followup.send(embed=ErrorEmbed(description="No hangar timers are currently being tracked."), ephemeral=True)
                return

            # Manually trigger the update task
            await self.update_hangar_embeds()

            # Also refresh cycle data
            new_cycle_start = await self._fetch_cycle_start()
            if new_cycle_start:
                self.cycle_start = new_cycle_start
                await self.bot.redis.set("qadir:hangar:cycle_start", str(new_cycle_start))

            await ctx.followup.send(
                embed=SuccessEmbed(
                    title="✅ Update Complete", description=f"Successfully updated {embed_count} hangar timer(s) and refreshed cycle data."
                ),
                ephemeral=True,
            )

        except Exception as e:
            logger.error(f"[HANGAR] Error in manual update: {e}")
            await ctx.followup.send(embed=ErrorEmbed(description="Failed to update hangar timers. Please try again."), ephemeral=True)


def setup(bot: Qadir) -> None:
    """
    Load the HangarCog into the bot.

    :param bot: The Qadir instance
    """

    bot.add_cog(HangarCog(bot))
