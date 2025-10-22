import logging
from typing import TYPE_CHECKING

import discord

from models.events import Event, LootEntry, LootItem
from utils.embeds import ErrorEmbed, SuccessEmbed
from utils.enums import EventStatus

logger = logging.getLogger("qadir")

if TYPE_CHECKING:
    from cogs.events import EventsCog


class AddLootModal(discord.ui.Modal):
    """Modal for adding loot items to an event."""

    def __init__(self, cog: "EventsCog", event: Event, items: list[LootItem], *args, **kwargs) -> None:
        super().__init__(title="Add Loot", *args, **kwargs)

        self.cog: "EventsCog" = cog
        self.redis = cog.redis

        self.event: Event = event
        self.items: list[LootItem] = items

        self.add_item(
            discord.ui.Select(
                select_type=discord.ComponentType.string_select,
                label="Select an item",
                description="Choose an item to add to the event loot",
                min_values=1,
                max_values=1,
                options=[discord.SelectOption(label=item.name, value=str(item.id)) for item in self.items],
            )
        )
        self.add_item(
            discord.ui.InputText(
                style=discord.InputTextStyle.short,
                label="Quantity",
                description="Enter the quantity of the item",
                placeholder="e.g., 1, 50, 3",
            )
        )

    async def on_error(self, _: discord.Interaction, error: Exception) -> None:
        logger.error("[MODAL] AddLootModal Error", exc_info=error)

    async def callback(self, interaction: discord.Interaction):
        """Handle the modal submission and add loot to the event."""

        await interaction.response.defer(ephemeral=True)

        # Check if user is a participant
        if str(interaction.user.id) not in self.event.participants:
            embed = ErrorEmbed("Not Participating", "You must join the event first using `/events join` before adding loot.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Check if event is active
        if self.event.status != EventStatus.ACTIVE:
            embed = ErrorEmbed("Event Inactive", f"This event is {self.event.status} and no longer accepts loot additions.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Get selected item ID from select menu
        select_menu: discord.ui.Select = self.children[0]
        selected_item_id: str = select_menu.values[0]

        # Find the item name from the items list
        selected_item = next((item for item in self.items if item.id == selected_item_id), None)
        if not selected_item:
            embed = ErrorEmbed("Not Found", "The selected item was not found.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        quantity_str = self.children[1].value.strip()

        # Validate quantity
        try:
            quantity = int(quantity_str)
            if quantity <= 0 or quantity >= 1000000000:
                raise ValueError("Quantity out of range")
        except ValueError:
            embed = ErrorEmbed("Invalid Quantity", "Please enter a positive number between `1` and `1,000,000,000`.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Add loot entry to the database
        self.event.loot_entries.append(LootEntry(item=selected_item, quantity=quantity, added_by=str(interaction.user.id)))
        await self.event.replace()

        # Invalidate the cache
        await self.redis.delete(f"{self.cog.REDIS_PREFIX}:{self.event.thread_id}")

        # Update the event card with new loot
        await self.cog.update_event_card(self.event)

        embed = SuccessEmbed(title="Loot Added", description=f"Added `{quantity}x {selected_item.name}` to the event loot")
        await interaction.followup.send(embed=embed, ephemeral=True)
