import json
import logging
from typing import TYPE_CHECKING

import discord

from ..embeds import ErrorEmbed, EventEmbed, SuccessEmbed
from ..enums import EventStatus

if TYPE_CHECKING:
    from cogs.events import EventsCog

logger = logging.getLogger("qadir")


class CreateEventModal(discord.ui.Modal):
    """Modal for creating a loot tracking event."""

    def __init__(self, cog: "EventsCog", *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.cog = cog
        self.redis = cog.redis
        self.db = cog.db

        self.add_item(discord.ui.InputText(label="Event Name", style=discord.InputTextStyle.short, required=True))
        self.add_item(discord.ui.InputText(label="Description", style=discord.InputTextStyle.long, required=False))

    async def on_error(self, _: discord.Interaction, error: Exception) -> None:
        logger.error("[MODAL] CreateEventModal Error", exc_info=error)

    async def callback(self, interaction: discord.Interaction):
        """Handle the modal submission and create an event thread."""

        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel

        if not isinstance(channel, discord.TextChannel):
            embed = ErrorEmbed("Invalid Channel", "Please use this command in a text channel.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        event_name = self.children[0].value
        description = self.children[1].value

        # Create thread for the event
        thread_title = f"🏆 {event_name}"
        thread = await channel.create_thread(name=thread_title, type=discord.ChannelType.public_thread)

        # Create event embed
        event_embed = EventEmbed(
            name=event_name,
            description=description,
            status=EventStatus.ACTIVE.value,
            participants=[str(interaction.user.id)],
            loot_entries=[],
        )
        event_embed.set_footer(text=f"Created by {interaction.user}", icon_url=interaction.user.display_avatar.url)

        # Instructions embed
        instructions_embed = discord.Embed(
            title="Participate",
            description=(
                "• Check the event card above for current totals and distribution\n"
                "• Use `/event join` to join this event\n"
                "• Use `/event loot` to add items you've collected\n"
                "• Event creator can use `/event finalize` to finalise the event"
            ),
            colour=0x0099FF,
        )

        message = await thread.send(embeds=[event_embed, instructions_embed])

        event_data = {
            "thread_id": str(thread.id),
            "message_id": str(message.id),
            "name": event_name,
            "description": description,
            "creator_id": str(interaction.user.id),
            "status": EventStatus.ACTIVE.value,
            "created_at": discord.utils.utcnow(),
            "participants": [str(interaction.user.id)],  # Creator is automatically a participant
            "loot_entries": [],
        }

        await self.db.insert_one(event_data)

        # Cache the event data
        await self.redis.set(f"{self.cog.REDIS_PREFIX}:{str(thread.id)}", json.dumps(event_data, default=str), ex=self.cog.REDIS_TTL)

        embed = SuccessEmbed(
            description=f"""Event **{event_name}** has been created in {thread.mention}!
            You've been automatically added as a participant.""",
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
