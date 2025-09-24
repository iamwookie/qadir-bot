import json
import logging
from datetime import datetime, timezone

import discord

from core import Qadir

logger = logging.getLogger("qadir")


class AddLootModal(discord.ui.Modal):
    """Modal for adding loot items to an event."""

    def __init__(self, event_thread_id: int, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.event_thread_id = event_thread_id

        self.add_item(discord.ui.InputText(
            label="Item Name",
            style=discord.InputTextStyle.short,
            required=True,
            placeholder="e.g., Dragon Sword, Gold Coins, Magic Potion"
        ))
        self.add_item(discord.ui.InputText(
            label="Quantity",
            style=discord.InputTextStyle.short,
            required=True,
            placeholder="e.g., 1, 50, 3"
        ))

    async def on_error(self, _: discord.Interaction, error: Exception) -> None:
        logger.error("[MODAL] AddLootModal Error", exc_info=error)

    async def callback(self, interaction: discord.Interaction):
        """Handle the modal submission and add loot to the event."""

        await interaction.response.defer(ephemeral=True)

        client: Qadir = interaction.client

        # Get event data from Redis
        event_data_raw = await client.redis.hget(f"qadir:event:{self.event_thread_id}", "data")
        if not event_data_raw:
            await interaction.followup.send("❌ Event not found or has been deleted.", ephemeral=True)
            return

        event_data = json.loads(event_data_raw)

        # Check if user is a participant
        if interaction.user.id not in event_data["participants"]:
            await interaction.followup.send(
                "❌ You must join the event first using `/join-event` before adding loot.",
                ephemeral=True
            )
            return

        # Check if event is active
        if event_data["status"] != "active":
            await interaction.followup.send(
                f"❌ This event is {event_data['status']} and no longer accepts loot additions.",
                ephemeral=True
            )
            return

        item_name = self.children[0].value.strip()
        quantity_str = self.children[1].value.strip()

        # Validate quantity
        try:
            quantity = int(quantity_str)
            if quantity <= 0:
                raise ValueError("Quantity must be positive")
        except ValueError:
            await interaction.followup.send(
                "❌ Invalid quantity. Please enter a positive number.",
                ephemeral=True
            )
            return

        # Add loot item
        loot_item = {
            "id": len(event_data["loot_items"]) + 1,
            "name": item_name,
            "quantity": quantity,
            "added_by": interaction.user.id,
            "added_at": datetime.now(timezone.utc).isoformat()
        }

        event_data["loot_items"].append(loot_item)

        # Update Redis
        await client.redis.hset(f"qadir:event:{self.event_thread_id}", "data", json.dumps(event_data))

        # Update the event message
        try:
            thread: discord.Thread = await client.fetch_channel(self.event_thread_id)
            message: discord.Message = await thread.fetch_message(event_data["message_id"])

            # Update the embed
            embed = message.embeds[0]
            embed.set_field_at(2, name="Total Loot Items", value=str(len(event_data["loot_items"])), inline=True)

            await message.edit(embeds=message.embeds)
        except Exception:
            logger.exception(f"[LOOT] Failed to update event message for event {self.event_thread_id}")

        await interaction.followup.send(
            f"✅ Added **{quantity}x {item_name}** to the event loot!",
            ephemeral=True
        )
