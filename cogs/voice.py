import logging

import discord

from config import config
from core import Cog, Qadir

logger = logging.getLogger("qadir")

CHANNEL_IDS = config["voice"]["channels"]


class VoiceCog(Cog, name="Voice"):
    """A cog to automatically connect to a voice channel on startup."""

    def __init__(self, bot):
        """
        Initialize the cog.

        Args:
            bot (Qadir): The bot instance to load the cog into
        """

        super().__init__(bot)

    async def _connect_to_channel(self, channel: discord.VoiceChannel) -> discord.VoiceClient:
        """Connect to a specific voice channel and deafen/mute the bot."""

        voice_client = channel.guild.voice_client

        # Handle the connection if one already exists
        if not voice_client:
            voice_client = await channel.connect()
            logger.debug(f"[VOICE] Connected To Channel: {channel.name} ({channel.id})")
        elif voice_client.is_connected():
            if voice_client.channel.id != channel.id:
                await voice_client.move_to(channel)
                logger.debug(f"[VOICE] Moved To Channel: {channel.name} ({channel.id})")
            else:
                logger.debug(f"[VOICE] Already Connected To Channel: {channel.name} ({channel.id})")
        else:
            await voice_client.disconnect(force=True)
            voice_client = await channel.connect()

        return voice_client

    @Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        """Handle voice state updates to deafen and mute the bot when it joins a channel."""

        # Filter for the bot's own voice state changes
        if member.id != self.bot.user.id:
            return

        # Mute and deafen if the bot is not already muted/deafened
        if after.channel and (not after.self_mute or not after.self_deaf):
            try:
                await after.channel.guild.change_voice_state(channel=after.channel, self_mute=True, self_deaf=True)
            except Exception:
                logger.exception(f"[VOICE] Failed To Mute/Deafen In Channel: {after.channel.name} ({after.channel.id})")

        # Reconnect if the bot was kicked/moved from a configured channel
        if before.channel and before.channel.id in CHANNEL_IDS and (not after.channel or after.channel.id not in CHANNEL_IDS):
            try:
                await self._connect_to_channel(before.channel)
            except Exception:
                logger.exception(f"[VOICE] Failed To Reconnect To Channel: {before.channel.name} ({before.channel.id})")
                return

    @Cog.listener()
    async def on_ready(self) -> None:
        """Connect to the configured voice channel when the bot is ready."""

        if not CHANNEL_IDS:
            logger.warning("[VOICE] No Channels Configured")
            return

        for channel_id in CHANNEL_IDS:
            try:
                channel = await self.bot.get_or_fetch(discord.VoiceChannel, channel_id)
                await self._connect_to_channel(channel)
            except discord.NotFound:
                logger.error(f"[VOICE] Channel Not Found: {channel_id}")
            except discord.Forbidden:
                logger.error(f"[VOICE] Missing Permissions To Connect To Channel: {channel_id}")
            except Exception:
                logger.exception(f"[VOICE] Failed To Connect To Channel: {channel_id}")


def setup(bot: Qadir) -> None:
    """
    Load the VoiceCog into the bot.

    Args:
        bot (Qadir): The bot instance to load the cog into.
    """

    bot.add_cog(VoiceCog(bot))
