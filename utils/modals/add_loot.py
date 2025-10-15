import logging
from typing import TYPE_CHECKING

import discord
from pymongo import ReturnDocument

from utils.embeds import ErrorEmbed, SuccessEmbed

logger = logging.getLogger("qadir")

if TYPE_CHECKING:
    from cogs.events import EventsCog


class AddLootModal(discord.ui.Modal):
    """Modal for adding loot items to an event."""

    def __init__(self, cog: "EventsCog", thread_id: int, event_data: dict, items_data: list[dict], *args, **kwargs) -> None:
        super().__init__(title="Add Loot", *args, **kwargs)

        self.cog = cog
        self.redis = cog.redis
        self.db = cog.db

        self.thread_id = thread_id
        self.event_data = event_data
        self.items_data = items_data

        self.add_item(
            discord.ui.Select(
                select_type=discord.ComponentType.string_select,
                label="Select an item",
                description="Choose an item to add to the event loot",
                min_values=1,
                max_values=1,
                options=[discord.SelectOption(label=item["name"], value=str(item["id"])) for item in self.items_data],
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
        if str(interaction.user.id) not in self.event_data["participants"]:
            embed = ErrorEmbed("Not Participating", "You must join the event first using `/events join` before adding loot.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Check if event is active
        if self.event_data["status"] != "active":
            embed = ErrorEmbed("Event Inactive", f"This event is {self.event_data['status']} and no longer accepts loot additions.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Get selected item ID from select menu
        select_menu: discord.ui.Select = self.children[0]
        selected_item_id = select_menu.values[0]

        # Find the item name from the items list
        selected_item = next((item for item in self.items_data if item["id"] == selected_item_id), None)
        if not selected_item:
            embed = ErrorEmbed("Not Found", "The selected item was not found.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        item_name = selected_item["name"]
        quantity_str = self.children[1].value.strip()

        # Validate quantity
        try:
            quantity = int(quantity_str)
            if quantity <= 0:
                raise ValueError("Quantity must be positive")
        except ValueError:
            embed = ErrorEmbed("Invalid Quantity", "Invalid quantity. Please enter a positive number. e.g. 10")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        self.event_data = await self.db.find_one_and_update(
            {"thread_id": str(self.thread_id)},
            {
                "$push": {
                    "loot_entries": {
                        "id": len(self.event_data["loot_entries"]) + 1,
                        "item": selected_item,  # Use the actual item ID from the selected item
                        "quantity": quantity,
                        "added_by": str(interaction.user.id),
                        "added_at": discord.utils.utcnow(),
                    }
                }
            },
            return_document=ReturnDocument.AFTER,
        )

        # Invalidate the cache
        await self.redis.delete(f"{self.cog.REDIS_PREFIX}:{str(self.thread_id)}")

        # Update the event card with new loot
        await self.cog.update_event_card(self.event_data)

        embed = SuccessEmbed(title="Loot Added", description=f"Added **{quantity}x {item_name}** to the event loot!")
        await interaction.followup.send(embed=embed, ephemeral=True)
