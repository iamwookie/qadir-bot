import discord


class EventEmbed(discord.Embed):
    """
    A custom embed class for displaying event information.
    """

    def __init__(self, name: str, description: str, status: str, participants: list, loot_entries: list, **kwargs) -> None:
        super().__init__(
            title=f"Event: {name}",
            description=description,
            colour=discord.Colour.green() if status == "active" else discord.Colour.red(),
            **kwargs,
        )

        self.data = {
            "name": name,
            "description": description,
            "status": status,
            "participants": participants,
            "loot_entries": loot_entries,
        }

        status_emoji = "🟢" if self.data["status"] == "active" else "🔴"

        self.add_field(name="Status", value=f"{status_emoji} `{self.data['status'].capitalize()}`", inline=True)
        self.add_field(name="Total Participants", value=f"`{len(self.data['participants'])}`", inline=True)
        self.add_field(name="Total Items", value=f"`{self.total_items()}`", inline=True)

        participants = ", ".join([f"<@{participant_id}>" for participant_id in self.data["participants"]])

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

        if not self.data.get("loot_entries"):
            return 0

        # Use a set to store unique item IDs
        unique_item_ids = set()

        for entry in self.data["loot_entries"]:
            item_id = entry["item"]["id"]
            unique_item_ids.add(item_id)

        return len(unique_item_ids)

    def loot_breakdown(self) -> str:
        """
        Generate a loot breakdown string for the embed showing contributions per participant.

        Returns:
            str: Formatted loot breakdown by participant
        """

        if not self.data.get("loot_entries"):
            return "*No loot added yet - use `/event loot` to contribute!*"

        # Aggregate by user and item
        user_item_totals = {}
        for entry in self.data["loot_entries"]:
            user_id = entry["added_by"]
            item_id = entry["item"]["id"]
            item_name = entry["item"]["name"]
            quantity = entry["quantity"]

            if user_id not in user_item_totals:
                user_item_totals[user_id] = {}

            if item_id in user_item_totals[user_id]:
                user_item_totals[user_id][item_id]["quantity"] += quantity
            else:
                user_item_totals[user_id][item_id] = {"name": item_name, "quantity": quantity}

        # Create breakdown lines per user
        breakdown_lines = []
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

        if not self.data.get("loot_entries"):
            return "*Distribution will be calculated once loot is added.*"

        participant_count = len(self.data["participants"])

        # Aggregate quantities by item ID
        loot_summary = {}
        for entry in self.data["loot_entries"]:
            item_id = entry["item"]["id"]
            item_name = entry["item"]["name"]
            quantity = entry["quantity"]

            if item_id in loot_summary:
                loot_summary[item_id]["quantity"] += quantity
            else:
                loot_summary[item_id] = {"name": item_name, "quantity": quantity}

        # Create distribution lines
        distribution_lines = []
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
