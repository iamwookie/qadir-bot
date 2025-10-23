import discord

from models.events import LootEntry
from utils.enums import EventStatus


class EventEmbed(discord.Embed):
    """A custom embed class for displaying event information."""

    def __init__(self, name: str, desc: str, status: EventStatus, participants: list[str], loot_entries: list[LootEntry], **kwargs) -> None:
        super().__init__(
            title=name,
            description=desc,
            colour=discord.Colour.green() if status == EventStatus.ACTIVE else discord.Colour.red(),
            **kwargs,
        )

        self._name = name
        self._desc = desc
        self._status = status
        self._participants = participants
        self._loot_entries = loot_entries

        status_emoji = "🟢" if self._status == EventStatus.ACTIVE else "🔴"

        self.add_field(name="Status", value=f"{status_emoji} `{self._status.name.capitalize()}`", inline=True)
        self.add_field(name="Total Participants", value=f"`{len(self._participants)}`", inline=True)
        self.add_field(name="Total Items", value=f"`{self.total_items()}`", inline=True)

        participants = ", ".join([f"<@{participant_id}>" for participant_id in self._participants]) or "*No participants yet*"

        self.add_field(name="Participants", value=participants[:1024], inline=False)
        self.add_field(name="Loot Breakdown", value=self.loot_breakdown(), inline=False)
        self.add_field(name="Distribution Preview", value=self.loot_distribution(), inline=False)

        self.timestamp = discord.utils.utcnow()

    def total_items(self) -> int:
        """
        Calculate the total number of unique items from loot entries.
        Aggregates entries with the same item ID as one item type.

        Returns:
            int: The number of unique item types (not quantities)
        """

        if not self._loot_entries:
            return 0

        # Use a set to store unique item IDs
        unique_item_ids = set()

        for entry in self._loot_entries:
            item_id = entry.item.id
            unique_item_ids.add(item_id)

        return len(unique_item_ids)

    def loot_breakdown(self) -> str:
        """
        Generate a loot breakdown string for the embed showing contributions per participant.

        Returns:
            str: Formatted loot breakdown by participant
        """

        if not self._loot_entries:
            return "*No loot added yet - use `/event loot` to contribute!*"

        # Aggregate by user and item
        user_item_totals: dict[int, dict[int, dict[str, int]]] = {}
        for entry in self._loot_entries:
            user_id = entry.added_by
            item_id = entry.item.id
            item_name = entry.item.name
            quantity = entry.quantity

            if user_id not in user_item_totals:
                user_item_totals[user_id] = {}

            if item_id in user_item_totals[user_id]:
                user_item_totals[user_id][item_id]["quantity"] += quantity
            else:
                user_item_totals[user_id][item_id] = {"name": item_name, "quantity": quantity}

        # Create breakdown lines per user
        breakdown_lines: list[str] = []
        for user_id in sorted(user_item_totals.keys()):
            user_mention = f"<@{user_id}>"
            user_items = []
            for item_data in user_item_totals[user_id].values():
                user_items.append(f"`{item_data['quantity']}x {item_data['name']}`")
            breakdown_lines.append(f"**{user_mention}**: {', '.join(user_items)}")

        return "\n".join(breakdown_lines)

    def loot_distribution(self) -> str:
        """
        Generate a loot distribution string for the embed.

        Returns:
            str: Formatted loot distribution
        """

        if not self._loot_entries:
            return "*Distribution will be calculated once loot is added.*"

        participant_count = len(self._participants)

        # Aggregate quantities by item ID
        loot_summary: dict[int, dict[str, int]] = {}
        for entry in self._loot_entries:
            item_id = entry.item.id
            item_name = entry.item.name
            quantity = entry.quantity

            if item_id in loot_summary:
                loot_summary[item_id]["quantity"] += quantity
            else:
                loot_summary[item_id] = {"name": item_name, "quantity": quantity}

        # Create distribution lines
        distribution_lines: list[str] = []
        for data in loot_summary.values():
            total_quantity = data["quantity"]
            item_name = data["name"]
            per_person = total_quantity // participant_count
            remainder = total_quantity % participant_count

            if remainder > 0:
                distribution_lines.append(f"**{total_quantity}x {item_name}** → {per_person} each + {remainder} extra")
            else:
                distribution_lines.append(f"**{total_quantity}x {item_name}** → {per_person} each")

        return "\n".join(distribution_lines)
