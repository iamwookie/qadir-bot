from typing import TYPE_CHECKING

import discord

from models.events import Event
from utils.embeds import ErrorEmbed, SuccessEmbed

if TYPE_CHECKING:
    from cogs.events import EventsCog


class EventSelectionView(discord.ui.View):
    """View for selecting events with dropdown (currently only used for joining)."""

    def __init__(self, cog: "EventsCog", events: list[Event], user_id: int):
        super().__init__(timeout=300)

        self.cog: "EventsCog" = cog
        self.events: list[Event] = events
        self.user_id: int = user_id

        select = EventSelect(self.cog, self.events, self.user_id)
        self.add_item(select)


class EventSelect(discord.ui.Select):
    """Dropdown for event selection."""

    def __init__(self, cog: "EventsCog", events: list[Event], user_id: int):
        super().__init__(placeholder="Choose an event to join...", min_values=1, max_values=1)

        self.cog: "EventsCog" = cog
        self.redis = cog.redis
        self.events: list[Event] = events
        self.user_id: int = user_id

        for event in self.events:
            is_participant = str(self.user_id) in event.participants
            participant_text = "Already joined" if is_participant else f"{len(event.participants)} participants"
            description = f"{participant_text} • {len(event.loot_entries)} items"
            emoji = "✅" if is_participant else "🏆"
            self.add_option(
                discord.SelectOption(label=event.name[:100], value=str(event.thread_id), description=description[:100], emoji=emoji)
            )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        selected_thread_id = int(self.values[0])

        event = await self.cog.get_or_fetch_event_by_id(selected_thread_id)
        if not event:
            embed = ErrorEmbed(title="Event Not Found", description="The event you are trying to join does not exist.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Check if user is already a participant
        if str(interaction.user.id) in event.participants:
            embed = SuccessEmbed(title="Already Participating", description="You're already participating in this event.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Add user to participants
        event.participants.append(str(interaction.user.id))
        await event.replace()

        # Invalidate relevant caches
        pipeline = self.redis.pipeline()
        pipeline.delete(f"{self.cog.REDIS_PREFIX}:{str(selected_thread_id)}")
        pipeline.delete(f"{self.cog.REDIS_PREFIX}:active")
        pipeline.delete(f"{self.cog.REDIS_PREFIX}:user:{interaction.user.id}")
        await pipeline.exec()

        # Update the event card with new participant
        await self.cog.update_event_card(event)

        embed = SuccessEmbed(title="Joined Event", description=f"You have successfully joined **{event.name}**.")
        await interaction.followup.send(embed=embed, ephemeral=True)
