import json
import logging
from collections import defaultdict
from datetime import datetime, timezone

import discord

from config import config
from core import Cog, Qadir
from core.embeds import ErrorEmbed, SuccessEmbed
from modals import AddLootModal, CreateEventModal

GUILD_IDS: list[int] = config["events"]["guilds"]
CHANNEL_IDS: list[int] = config["events"]["channels"]

logger = logging.getLogger("qadir")


class EventSelectionView(discord.ui.View):
    """View for selecting events with dropdown (currently only used for joining)."""

    def __init__(self, cog: "EventsCog", events: list, user_id: int, action: str):
        super().__init__(timeout=300)

        self.cog = cog
        self.events = events
        self.user_id = user_id
        self.action = action

        # Create dropdown with events
        options = []
        for event in events:
            # Check if user is already in this event
            is_member = user_id in event["participants"]
            emoji = "✅" if is_member else "🏆"
            participant_text = "Already joined" if is_member else f"{len(event['participants'])} participants"
            description = f"{participant_text} • {len(event['loot_entries'])} items"

            options.append(
                discord.SelectOption(label=event["name"][:100], value=str(event["thread_id"]), description=description[:100], emoji=emoji)
            )

        if options:
            select = EventSelect(self.cog, options, self.action)
            self.add_item(select)


class EventSelect(discord.ui.Select):
    """Dropdown for event selection (currently only used for joining)."""

    def __init__(self, cog: "EventsCog", options: list, action: str):
        super().__init__(placeholder=f"Choose an event to {action}...", options=options, min_values=1, max_values=1)

        self.cog = cog
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        selected_thread_id = int(self.values[0])

        # Only handle join action since loot is now thread-only
        if self.action == "join":
            await interaction.response.defer(ephemeral=True)

            event_data_raw = await self.cog.bot.redis.get(f"qadir:event:{selected_thread_id}")
            if not event_data_raw:
                await interaction.followup.send("❌ Event not found.", ephemeral=True)
                return

            event_data = json.loads(event_data_raw)

            # Check if user is already a participant
            if interaction.user.id in event_data["participants"]:
                await interaction.followup.send("✅ You're already participating in this event!", ephemeral=True)
                return

            # Add user to participants
            event_data["participants"].append(interaction.user.id)

            # Update Redis
            await self.cog.bot.redis.set(f"qadir:event:{selected_thread_id}", json.dumps(event_data))

            # Update the event card with new participant
            await self.cog._update_event_card(event_data)

            await interaction.followup.send(
                f"🎉 Successfully joined **{event_data['name']}**!\n" f"You can now add loot items to this event.", ephemeral=True
            )
        else:
            # This shouldn't happen anymore, but just in case
            await interaction.response.send_message(f"❌ Unknown action: {self.action}", ephemeral=True)


class EventsCog(Cog, name="Events", guild_ids=GUILD_IDS):
    """
    A cog to manage loot tracking events where participants can add items
    they've collected and see automatic distribution calculations.
    """

    async def _get_user_active_events(self, user_id: int) -> list:
        """
        Get a list of active events that a user is participating in.

        Args:
            user_id (int): The Discord user ID to check for active events.
        Returns:
            A list of active event dictionaries that the user participates in.
        """

        event_ids = await self.bot.redis.smembers("qadir:events")
        user_events = []

        for event_id in event_ids:
            event_data_raw = await self.bot.redis.get(f"qadir:event:{event_id}")
            if not event_data_raw:
                continue

            event_data = json.loads(event_data_raw)
            if event_data["status"] == "active" and user_id in event_data["participants"]:
                user_events.append(event_data)

        return user_events

    async def _update_event_card(self, event_data: dict) -> None:
        """Update an event card with current loot breakdown and distribution.

        Args:
            event_data (dict): The event data to update the card with.
        """

        try:
            thread_id = int(event_data["thread_id"])
            message_id = int(event_data["message_id"])

            # Use get_channel instead of fetch_channel for cached access
            thread = self.bot.get_channel(thread_id)
            if not thread:
                thread = await self.bot.fetch_channel(thread_id)

            # Fetch message (this is unavoidable but only one API call)
            message = await thread.fetch_message(message_id)

            # Get the original embed
            event_embed = message.embeds[0].copy()

            # Update basic stats
            participant_count = len(event_data["participants"])
            total_items = len(event_data["loot_entries"])

            # Update the basic fields (Status, Participants, Total Items)
            event_embed.set_field_at(
                0, name="Status", value="🟢 Active" if event_data["status"] == "active" else "🔴 Completed", inline=True
            )
            event_embed.set_field_at(1, name="Participants", value=str(participant_count), inline=True)
            event_embed.set_field_at(2, name="Total Items", value=str(total_items), inline=True)

            # Create participant list using direct mentions
            participants = [f"<@{participant_id}>" for participant_id in event_data["participants"]]
            participant_text = ", ".join(participants) if participants else "No participants yet"

            # Calculate loot breakdown and distribution
            if event_data["loot_entries"]:
                # Group loot by item ID and by contributor
                item_names = {}  # item_id -> item_name (for display)
                loot_summary_by_id = defaultdict(int)  # item_id -> total_quantity
                user_item_totals = defaultdict(lambda: defaultdict(int))  # user_id -> item_id -> total_quantity

                # Process loot entries using direct mentions
                for entry in event_data["loot_entries"]:
                    item_id = entry["item"]["id"]
                    item_name = entry["item"]["name"]
                    quantity = entry["quantity"]
                    user_id = entry["added_by"]

                    # Group by item ID for accurate totals
                    loot_summary_by_id[item_id] += quantity
                    item_names[item_id] = item_name  # Store name for display

                    # Track individual contributions grouped by item type
                    user_item_totals[user_id][item_id] += quantity

                # Create loot breakdown text (combined per user per item)
                breakdown_lines = []
                for user_id in sorted(user_item_totals.keys()):
                    user_mention = f"<@{user_id}>"
                    user_items = []
                    for item_id, total_quantity in sorted(user_item_totals[user_id].items()):
                        item_name = item_names[item_id]
                        user_items.append(f"{total_quantity}x {item_name}")
                    breakdown_lines.append(f"**{user_mention}**: {', '.join(user_items)}")

                breakdown_text = "\n".join(breakdown_lines) if breakdown_lines else "No contributions yet"

                # Create distribution preview (grouped by item ID)
                distribution_lines = []
                for item_id, total_quantity in sorted(loot_summary_by_id.items()):
                    item_name = item_names[item_id]
                    per_person = total_quantity // participant_count
                    remainder = total_quantity % participant_count

                    if remainder > 0:
                        distribution_lines.append(f"**{total_quantity}x {item_name}** → {per_person} each + {remainder} extra")
                    else:
                        distribution_lines.append(f"**{total_quantity}x {item_name}** → {per_person} each")

                distribution_text = "\n".join(distribution_lines) if distribution_lines else "No items to distribute"

                # Update the embed fields
                event_embed.set_field_at(3, name="👥 Participants", value=participant_text[:1024], inline=False)
                event_embed.set_field_at(4, name="🎁 Loot Breakdown", value=breakdown_text[:1024], inline=False)  # Discord field limit
                event_embed.set_field_at(5, name="⚖️ Distribution Preview", value=distribution_text[:1024], inline=False)
            else:
                # No loot yet
                event_embed.set_field_at(3, name="👥 Participants", value=participant_text[:1024], inline=False)
                event_embed.set_field_at(
                    4, name="🎁 Loot Breakdown", value="*No loot added yet - use `/event loot` to contribute!*", inline=False
                )
                event_embed.set_field_at(
                    5, name="⚖️ Loot Distribution", value="*Distribution will be calculated once loot is added*", inline=False
                )

            # Update the message
            await message.edit(embeds=[event_embed, message.embeds[1]])  # Keep the instructions embed
            logger.info(f"[EVENT-CARD] Successfully Updated Event Card For {event_data['name']}")

        except Exception:
            logger.exception("[EVENT-CARD] Failed To Update Event Card")

    async def _get_all_active_events(self) -> list:
        """Get all active events."""

        try:
            logger.info("[REDIS] Getting All Event IDs From qadir:events")
            event_ids = await self.bot.redis.smembers("qadir:events")
            logger.info(f"[REDIS] Found {len(event_ids)} Event IDs: {list(event_ids)}")

            active_events = []

            for event_id in event_ids:
                logger.info(f"[REDIS] Fetching Data For Event {event_id} (type: {type(event_id)})")
                # Ensure event_id is a string for consistent key formatting
                event_id_str = str(event_id) if isinstance(event_id, int) else event_id
                event_data_raw = await self.bot.redis.get(f"qadir:event:{event_id_str}")

                if not event_data_raw:
                    logger.warning(f"[REDIS] No Data Found For Event {event_id}")
                    continue

                try:
                    event_data = json.loads(event_data_raw)
                    logger.info(
                        f"[REDIS] Event {event_id}: name='{event_data.get('name')}', status='{event_data.get('status')}', participants={len(event_data.get('participants', []))}"
                    )

                    if event_data["status"] == "active":
                        active_events.append(event_data)
                        logger.info(f"[REDIS] Added Active Event {event_id} To Results")
                    else:
                        logger.info(f"[REDIS] Skipping Event {event_id} (status: {event_data['status']})")

                except json.JSONDecodeError as e:
                    logger.error(f"[REDIS] Failed To Parse JSON For Event {event_id}: {e}")
                    continue

            logger.info(f"[REDIS] Returning {len(active_events)} Active Events")
            return active_events

        except Exception:
            logger.exception("[REDIS] Error In _get_all_active_events")
            return []

    # Main events command group
    event = discord.SlashCommandGroup("event", "Manage loot tracking events")

    @event.command(description="Create a new loot tracking event")
    async def create(self, ctx: discord.ApplicationContext) -> None:
        """
        Create a new loot tracking event where participants can add items and see automatic distribution.
        """

        # Check if command is used in allowed channels
        if ctx.channel_id not in CHANNEL_IDS:
            allowed_channels = [f"<#{channel_id}>" for channel_id in CHANNEL_IDS]
            embed = ErrorEmbed(description=f"This command can only be used in: {', '.join(allowed_channels)}")
            await ctx.respond(embed=embed, ephemeral=True)
            return

        modal = CreateEventModal(title="Create Loot Event")
        await ctx.send_modal(modal)

    @event.command(description="Join an active event to participate in loot tracking")
    async def join(self, ctx: discord.ApplicationContext) -> None:
        """
        Join an event.

        Args:
            ctx (discord.ApplicationContext): The context of the command.
        """

        # Check if this is run in an event thread
        if isinstance(ctx.channel, discord.Thread):
            thread_id = ctx.channel.id
            event_data_raw = await self.bot.redis.get(f"qadir:event:{thread_id}")

            if event_data_raw:
                # This is an event thread
                event_data = json.loads(event_data_raw)

                # Check if user is already a participant in this event
                if ctx.author.id in event_data["participants"]:
                    # User is already in this event
                    embed = SuccessEmbed(
                        title="✅ Already in This Event",
                        description=(
                            f"You're already participating in **{event_data['name']}**!\n\n"
                            f"**You can now:**\n"
                            f"• Use `/event loot` to add items you've collected\n"
                            f"• Check the event card above for current totals"
                        ),
                    )
                    await ctx.respond(embed=embed, ephemeral=True)
                    return
                else:
                    # User is not in this event, join them directly
                    await ctx.defer(ephemeral=True)

                    # Add user to participants
                    event_data["participants"].append(ctx.author.id)

                    # Update Redis
                    await self.bot.redis.set(f"qadir:event:{thread_id}", json.dumps(event_data))

                    # Update the event card with new participant
                    await self._update_event_card(event_data)

                    embed = SuccessEmbed(
                        title="🎉 Successfully Joined Event!",
                        description=(
                            f"Welcome to **{event_data['name']}**!\n\n"
                            f"**You can now:**\n"
                            f"• Use `/event loot` in this thread to add items\n"
                            f"• Check the event card above for current totals"
                        ),
                    )
                    await ctx.followup.send(embed=embed, ephemeral=True)
                    return

        await ctx.defer(ephemeral=True)

        # Get all active events
        all_events = await self._get_all_active_events()

        if not all_events:
            embed = ErrorEmbed(
                title="❌ No Active Events",
                description=(
                    "There are no active events to join right now.\n\n"
                    "**Want to create an event?**\n"
                    f"Use `/events create` in <#{CHANNEL_IDS[0]}>"
                ),
            )
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        # Filter events user can join (not already a member of)
        joinable_events = [event for event in all_events if ctx.author.id not in event["participants"]]

        if not joinable_events:
            # User is already in all events
            user_events = [event for event in all_events if ctx.author.id in event["participants"]]
            event_list = "\n".join([f"• 🏆 **{event['name']}**" for event in user_events])

            embed = SuccessEmbed(
                title="✅ Already in All Events!", description=f"You're already participating in all active events:\n\n{event_list}"
            )
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        # Show event selection
        embed = SuccessEmbed(title="🏆 Join an Event", description="Select an event to join from the dropdown below:")

        view = EventSelectionView(self, all_events, ctx.author.id, "join")
        await ctx.followup.send(embed=embed, view=view, ephemeral=True)

    @event.command(description="Add loot items you've collected to an event")
    async def loot(self, ctx: discord.ApplicationContext) -> None:
        """
        Add loot items collected to an event.
        This command can only be used in event threads.

        Args:
            ctx (discord.ApplicationContext): The context of the command.
        """

        thread_error_embed = ErrorEmbed(
            title="❌ Not in an event thread",
            description=(
                "This command can only be used in event threads.\n\n"
                "**To add loot:**\n"
                "1. Use `/event create` to create an event or `/event join` to join an event\n"
                "2. Go to the event thread\n"
                "3. Use `/event loot` in that thread\n\n"
                f"**Find or create events in:** <#{CHANNEL_IDS[0]}>"
            ),
        )

        # Check if this is run in an event thread
        if not isinstance(ctx.channel, discord.Thread):
            await ctx.respond(embed=thread_error_embed, ephemeral=True)
            return

        thread_id = ctx.channel.id
        event_data_raw = await self.bot.redis.get(f"qadir:event:{thread_id}")

        if not event_data_raw:
            await ctx.respond(embed=thread_error_embed, ephemeral=True)
            return

        event_data = json.loads(event_data_raw)

        # Check if user is a participant
        if ctx.author.id not in event_data["participants"]:
            embed = ErrorEmbed(
                title="Not a participant",
                description=("You must join this event before adding loot.\n" "Use `/event join` to join this event."),
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return

        # Fetch available items
        items_data_raw = await self.bot.redis.get("qadir:event:items")

        if not items_data_raw:
            embed = ErrorEmbed(
                title="No items configured",
                description="No items are configured for loot tracking. Please contact an administrator.",
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return

        items_data = json.loads(items_data_raw)

        # Show the AddLootModal
        modal = AddLootModal(self, thread_id, event_data, items_data, title=f"Add Loot to {event_data['name']}")
        await ctx.send_modal(modal)

    @event.command(description="Finalise and close an event you created")
    async def finalise(self, ctx: discord.ApplicationContext) -> None:
        """
        Finalise and close an event.

        Args:
            ctx (discord.ApplicationContext): The context of the command.
        """

        # Defer immediately to prevent timeout
        await ctx.defer(ephemeral=True)

        # Check if this is an event thread
        if not isinstance(ctx.channel, discord.Thread):
            embed = ErrorEmbed(description="This command can only be used in event threads.")
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        thread_id = ctx.channel.id
        event_data_raw = await self.bot.redis.get(f"qadir:event:{thread_id}")

        if not event_data_raw:
            embed = ErrorEmbed(description="This thread is not associated with an active event.")
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        event_data = json.loads(event_data_raw)

        # Check if user is the event creator
        creator_id = event_data["creator_id"]
        current_user_id = ctx.author.id

        if current_user_id != creator_id:
            logger.warning(f"[FINALISE] Permission Denied - User {current_user_id} Is Not Creator {creator_id}")
            embed = ErrorEmbed(
                title="❌ Permission Denied",
                description=f"Only the event creator can finalise the event.\n\nEvent creator: <@{creator_id}>\nYou are: <@{current_user_id}>",
            )
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        logger.info(f"[FINALISE] Permission Check Passed - User {current_user_id} Is The Creator")

        # Check if event is already finalised
        if event_data["status"] != "active":
            logger.warning(f"[FINALISE] Event {thread_id} Is Not Active")
            embed = ErrorEmbed(description=f"This event is already {event_data['status']}.")
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        # Update event status
        event_data["status"] = "completed"
        event_data["finalised_at"] = datetime.now(timezone.utc).timestamp()

        # Update Redis
        await self.bot.redis.set(f"qadir:event:{thread_id}", json.dumps(event_data))

        # Update the event message
        try:
            message: discord.Message = await ctx.channel.fetch_message(event_data["message_id"])
            embed = message.embeds[0]
            embed.colour = 0xFF0000
            embed.set_field_at(0, name="Status", value="🔴 Completed", inline=True)
            await message.edit(embeds=message.embeds)
        except Exception:
            logger.exception(f"[FINALISE] Failed To Update Event Message For Event {thread_id}")

        # Create dramatic finalization announcement
        if event_data["loot_entries"]:
            # Collect all unique user IDs (contributors + participants)
            all_user_ids = set(event_data["participants"])
            for entry in event_data["loot_entries"]:
                all_user_ids.add(entry["added_by"])

            # Batch fetch all users at once
            user_cache = {}
            for user_id in all_user_ids:
                try:
                    user = self.bot.get_user(user_id)
                    if not user:
                        user = await self.bot.fetch_user(user_id)
                    user_cache[user_id] = {"display_name": user.display_name, "mention": user.mention}
                except Exception:
                    user_cache[user_id] = {"display_name": f"User {user_id}", "mention": f"<@{user_id}>"}

            # Calculate final totals using cached user data
            item_names = {}  # item_id -> item_name (for display)
            loot_summary_by_id = defaultdict(int)  # item_id -> total_quantity
            user_item_totals = defaultdict(lambda: defaultdict(int))  # user_id -> item_id -> total_quantity

            for entry in event_data["loot_entries"]:
                item_id = entry["item"]["id"]
                item_name = entry["item"]["name"]
                quantity = entry["quantity"]
                user_id = entry["added_by"]

                # Group by item ID for accurate totals
                loot_summary_by_id[item_id] += quantity
                item_names[item_id] = item_name

                # Track individual contributions grouped by item type
                user_item_totals[user_id][item_id] += quantity

            # Create user contributions grouped by item type
            loot_by_user = {}
            for user_id, items in user_item_totals.items():
                user_mention = user_cache[user_id]["mention"]
                user_items = []
                for item_id, total_quantity in sorted(items.items()):
                    item_name = item_names[item_id]
                    user_items.append(f"{total_quantity}x {item_name}")
                loot_by_user[user_mention] = user_items  # Create the main announcement embed
            final_embed = discord.Embed(
                title=f"🏁 EVENT FINALISED: {event_data['name']}",
                description="The adventure has concluded! Here's what everyone contributed and earned:",
                colour=0xFFD700,  # Gold color for dramatic effect
            )

            # Add contributions section with mentions
            if loot_by_user:
                contribution_lines = []
                for user_mention, items in sorted(loot_by_user.items()):
                    contribution_lines.append(f"{user_mention} contributed: **{', '.join(items)}**")

                final_embed.add_field(name="🎒 Individual Contributions", value="\n".join(contribution_lines), inline=False)

            # Add distribution section with mentions for who gets what (using cached data)
            participant_mentions = [user_cache[participant_id]["mention"] for participant_id in event_data["participants"]]

            distribution_lines = []
            individual_shares = []

            for item_id, total_quantity in sorted(loot_summary_by_id.items()):
                item_name = item_names[item_id]
                per_person = total_quantity // len(event_data["participants"])
                remainder = total_quantity % len(event_data["participants"])

                if per_person > 0:
                    if remainder > 0:
                        distribution_lines.append(f"**{total_quantity}x {item_name}** → {per_person} each + {remainder} extra")
                        individual_shares.append(f"• **{per_person}x {item_name}** each")
                    else:
                        distribution_lines.append(f"**{total_quantity}x {item_name}** → {per_person} each")
                        individual_shares.append(f"• **{per_person}x {item_name}** each")

            final_embed.add_field(name="⚖️ Final Distribution Breakdown", value="\n".join(distribution_lines), inline=False)

            # Add what each person gets
            if individual_shares:
                share_text = f"Each participant ({', '.join(participant_mentions)}) receives:\n" + "\n".join(individual_shares)
                final_embed.add_field(name="🎁 Your Share", value=share_text, inline=False)

            final_embed.set_footer(text="Event has been locked. No more changes can be made.")
            final_embed.timestamp = datetime.now(timezone.utc)

            # Send to the thread
            await ctx.followup.send(embed=final_embed, ephemeral=False)

            # Also send a summary to the main channel
            try:
                main_channel = await self.bot.fetch_channel(CHANNEL_IDS[0])
                summary_embed = discord.Embed(
                    title=f"📢 Event Completed: {event_data['name']}",
                    description=f"Event has been finalised with {len(event_data['participants'])} participants and {len(event_data['loot_entries'])} items!",
                    colour=0x00FF00,
                )
                summary_embed.add_field(name="Participants", value=", ".join(participant_mentions), inline=False)

                # Add top contributors
                if loot_by_user:
                    top_contributors = sorted(loot_by_user.items(), key=lambda x: len(x[1]), reverse=True)[:3]
                    contributor_text = []
                    for user_mention, items in top_contributors:
                        contributor_text.append(f"{user_mention}: {len(items)} items")
                    summary_embed.add_field(name="Top Contributors", value="\n".join(contributor_text), inline=True)

                await main_channel.send(embed=summary_embed)
                pass

            except Exception as e:
                logger.error(f"Failed to send main channel announcement: {e}")

        else:
            await ctx.followup.send("🏁 Event finalised! No loot was collected during this event.", ephemeral=False)

        # Lock the thread
        await ctx.channel.edit(locked=True)

    @event.command(description="Show all events you've created or joined")
    async def list(self, ctx: discord.ApplicationContext) -> None:
        """
        Lists all active events that the user has created or joined.
        This command retrieves all active events from Redis, categorizes them into events created by the user and events the user has joined,
        and displays them in an embedded message. If the user has not created or joined any events, a message is shown indicating so.

        Args:
            ctx (discord.ApplicationContext): The context of the command invocation.
        Returns:
            None
        """

        await ctx.defer(ephemeral=True)

        # Get all active events
        event_ids = await self.bot.redis.smembers("qadir:events")

        user_events = []
        participated_events = []

        for event_id in event_ids:
            event_data_raw = await self.bot.redis.get(f"qadir:event:{event_id}")
            if not event_data_raw:
                continue

            event_data = json.loads(event_data_raw)

            if event_data["creator_id"] == ctx.author.id:
                user_events.append(event_data)
            elif ctx.author.id in event_data["participants"]:
                participated_events.append(event_data)

        embed = SuccessEmbed(title="📋 Your Events")

        if user_events:
            created_text = []
            for event in user_events:
                status_emoji = "🟢" if event["status"] == "active" else "🔴"
                created_text.append(
                    f"{status_emoji} **{event['name']}** ({len(event['participants'])} participants, {len(event['loot_entries'])} items)"
                )

            embed.add_field(name="🏆 Events You Created", value="\n".join(created_text), inline=False)

        if participated_events:
            participated_text = []
            for event in participated_events:
                status_emoji = "🟢" if event["status"] == "active" else "🔴"
                participated_text.append(
                    f"{status_emoji} **{event['name']}** ({len(event['participants'])} participants, {len(event['loot_entries'])} items)"
                )

            embed.add_field(name="🎯 Events You Joined", value="\n".join(participated_text), inline=False)

        if not user_events and not participated_events:
            embed.description = "You haven't created or joined any events yet."

        await ctx.followup.send(embed=embed, ephemeral=True)


def setup(bot: Qadir) -> None:
    """
    Load the EventsCog into the bot.

    Args:
        bot (Qadir): The bot instance to load the cog into.
    """

    bot.add_cog(EventsCog(bot))
