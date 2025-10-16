from typing import TYPE_CHECKING

import discord

from models.events import Event

if TYPE_CHECKING:
    from cogs.events import EventsCog


class EventSelectionView(discord.ui.View):
    """View for selecting events with dropdown (currently only used for joining)."""

    def __init__(self, cog: "EventsCog", events: list[Event], user_id: int):
        super().__init__(timeout=300)

        self.cog: "EventsCog" = cog
        self.events: list[Event] = events
        self.user_id: int = user_id

        # Create dropdown with events
        options = []
        for event in events:
            # Check if user is already in this event
            is_participant = str(user_id) in event.participants
            emoji = "✅" if is_participant else "🏆"
            participant_text = "Already joined" if is_participant else f"{len(event.participants)} participants"
            description = f"{participant_text} • {len(event.loot_entries)} items"

            options.append(
                discord.SelectOption(label=event.name[:100], value=str(event.thread_id), description=description[:100], emoji=emoji)
            )

        if options:
            select = EventSelect(self.cog, options)
            self.add_item(select)


class EventSelect(discord.ui.Select):
    """Dropdown for event selection."""

    def __init__(self, cog: "EventsCog", options: list):
        super().__init__(placeholder="Choose an event to join...", options=options, min_values=1, max_values=1)

        self.cog = cog
        self.redis = cog.redis
        self.db = cog.db

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        selected_thread_id = int(self.values[0])

        event_data = await self.cog.fetch_event_by_id(selected_thread_id)
        if not event_data:
            await interaction.followup.send("❌ Event not found.", ephemeral=True)
            return

        # Check if user is already a participant
        if str(interaction.user.id) in event_data["participants"]:
            await interaction.followup.send("✅ You're already participating in this event!", ephemeral=True)
            return

        # Add user to participants
        await self.cog.db.update_one({"thread_id": str(selected_thread_id)}, {"$push": {"participants": str(interaction.user.id)}})

        # Invalidate relevant caches
        pipeline = self.redis.pipeline()
        pipeline.delete(f"{self.cog.REDIS_PREFIX}:{str(selected_thread_id)}")
        pipeline.delete(f"{self.cog.REDIS_PREFIX}:active")
        pipeline.delete(f"{self.cog.REDIS_PREFIX}:user:{interaction.user.id}")
        await pipeline.exec()

        # Update the event card with new participant
        await self.cog.update_event_card(event_data)

        await interaction.followup.send(
            f"🎉 Successfully joined **{event_data['name']}**!\n" f"You can now add loot items to this event.", ephemeral=True
        )
