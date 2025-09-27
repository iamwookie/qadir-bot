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
    """View for selecting events with dropdown."""

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
            description = f"{participant_text} • {len(event['loot_items'])} items"

            options.append(
                discord.SelectOption(label=event["name"][:100], value=str(event["thread_id"]), description=description[:100], emoji=emoji)
            )

        if options:
            select = EventSelect(self.cog, options, self.action)
            self.add_item(select)


class EventSelect(discord.ui.Select):
    """Dropdown for event selection."""

    def __init__(self, cog: "EventsCog", options: list, action: str):
        super().__init__(placeholder=f"Choose an event to {action}...", options=options, min_values=1, max_values=1)

        self.cog = cog
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        selected_thread_id = int(self.values[0])

        # Handle loot differently since it needs to send a modal (can't defer first)
        if self.action == "loot":
            await self.cog._handle_loot(interaction, selected_thread_id)
        elif self.action == "join":
            await self.cog._handle_join(interaction, selected_thread_id)


class EventsCog(Cog, name="Events", guild_ids=GUILD_IDS):
    """
    A cog to manage loot tracking events where participants can add items
    they've collected and see automatic distribution calculations.
    """

    async def _get_user_active_events(self, user_id: int) -> list:
        """Get a list of active events that a user is participating in.

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
            total_items = len(event_data["loot_items"])

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
            if event_data["loot_items"]:
                from collections import defaultdict

                # Group loot by type and by contributor
                loot_summary = defaultdict(int)
                loot_by_user = defaultdict(list)

                # Process loot items using direct mentions
                for item in event_data["loot_items"]:
                    loot_summary[item["name"]] += item["quantity"]
                    user_mention = f"<@{item['added_by']}>"
                    loot_by_user[user_mention].append(f"{item['quantity']}x {item['name']}")

                # Create loot breakdown text
                breakdown_lines = []
                for user_mention, items in sorted(loot_by_user.items()):
                    breakdown_lines.append(f"**{user_mention}**: {', '.join(items)}")

                breakdown_text = "\n".join(breakdown_lines) if breakdown_lines else "No contributions yet"

                # Create distribution preview
                distribution_lines = []
                for item_name, total_quantity in sorted(loot_summary.items()):
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
                    4, name="🎁 Current Loot Breakdown", value="*No loot added yet - use `/event loot` to contribute!*", inline=False
                )
                event_embed.set_field_at(
                    5, name="⚖️ Distribution Preview", value="*Distribution will be calculated once loot is added*", inline=False
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

    async def _handle_join(self, interaction: discord.Interaction, thread_id: int):
        """
        Handle joining an event via dropdown selection.

        Args:
            interaction (discord.Interaction): The interaction object.
            thread_id (int): The ID of the event thread to join.
        """

        await interaction.response.defer(ephemeral=True)

        event_data_raw = await self.bot.redis.get(f"qadir:event:{thread_id}")
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
        await self.bot.redis.set(f"qadir:event:{thread_id}", json.dumps(event_data))

        # Update the event card with new participant
        await self._update_event_card(event_data)

        await interaction.followup.send(
            f"🎉 Successfully joined **{event_data['name']}**!\n" f"You can now add loot items to this event.", ephemeral=True
        )

    async def _handle_loot(self, interaction: discord.Interaction, thread_id: int):
        """Handle adding loot via dropdown selection."""

        event_data_raw = await self.bot.redis.get(f"qadir:event:{thread_id}")
        if not event_data_raw:
            await interaction.response.send_message("❌ Event not found.", ephemeral=True)
            return

        event_data = json.loads(event_data_raw)

        # Check if user is a participant
        if interaction.user.id not in event_data["participants"]:
            await interaction.response.send_message(
                f"❌ You must join **{event_data['name']}** first before adding loot.\n" f"Use `/join-event` to join this event.",
                ephemeral=True,
            )
            return

        # Open the add loot modal
        modal = AddLootModal(self, event_thread_id=thread_id, title=f"Add Loot to {event_data['name']}")
        await interaction.response.send_modal(modal)

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

                # Check if user is a participant in this event
                if ctx.author.id in event_data["participants"]:
                    # User is in this event, show the add loot modal directly
                    modal = AddLootModal(self, event_thread_id=thread_id, title=f"Add Loot to {event_data['name']}")
                    await ctx.send_modal(modal)
                    return
                else:
                    # User is not in this event
                    embed = ErrorEmbed(
                        title="❌ Not in This Event",
                        description=(
                            f"You're not participating in **{event_data['name']}**.\n\n"
                            f"**To add loot to this event:**\n"
                            f"Use `/event join` to join this event first.\n\n"
                            f"**Or use this command outside the thread** to add loot to other events you're in."
                        ),
                    )
                    await ctx.respond(embed=embed, ephemeral=True)
                    return

        # Defer the response as no more modals will be sent
        await ctx.defer(ephemeral=True)

        # Get user's active events
        user_events = await self._get_user_active_events(ctx.author.id)

        if not user_events:
            embed = ErrorEmbed(
                title="❌ Not in Any Events",
                description=(
                    "You're not participating in any active events.\n\n"
                    "**To add loot, you need to:**\n"
                    "1. Use `/event join` to join an existing event\n"
                    "2. Or use `/event create` to create a new event\n\n"
                    f"**Create events in:** <#{CHANNEL_IDS[0]}>"
                ),
            )
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        # Show event selection for adding loot
        embed = SuccessEmbed(title="🎒 Add Loot to Event", description="Select which event to add your loot items to:")

        view = EventSelectionView(self, user_events, ctx.author.id, "loot")
        await ctx.followup.send(embed=embed, view=view, ephemeral=True)

    @event.command(description="Finalise and close event with final distribution (event creator only)")
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
        event_data["finalised_at"] = datetime.now(timezone.utc).isoformat()

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
        if event_data["loot_items"]:
            # Collect all unique user IDs (contributors + participants)
            all_user_ids = set(event_data["participants"])
            for item in event_data["loot_items"]:
                all_user_ids.add(item["added_by"])

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
            loot_summary = defaultdict(int)
            loot_by_user = defaultdict(list)

            for item in event_data["loot_items"]:
                loot_summary[item["name"]] += item["quantity"]
                user_mention = user_cache[item["added_by"]]["mention"]
                loot_by_user[user_mention].append(f"{item['quantity']}x {item['name']}")

            # Create the main announcement embed
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

            for item_name, total_quantity in sorted(loot_summary.items()):
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
                    description=f"Event has been finalised with {len(event_data['participants'])} participants and {len(event_data['loot_items'])} items!",
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
                    f"{status_emoji} **{event['name']}** ({len(event['participants'])} participants, {len(event['loot_items'])} items)"
                )

            embed.add_field(name="🏆 Events You Created", value="\n".join(created_text), inline=False)

        if participated_events:
            participated_text = []
            for event in participated_events:
                status_emoji = "🟢" if event["status"] == "active" else "🔴"
                participated_text.append(
                    f"{status_emoji} **{event['name']}** ({len(event['participants'])} participants, {len(event['loot_items'])} items)"
                )

            embed.add_field(name="🎯 Events You Joined", value="\n".join(participated_text), inline=False)

        if not user_events and not participated_events:
            embed.description = "You haven't created or joined any events yet."

        await ctx.followup.send(embed=embed, ephemeral=True)

    @event.command(description="Check your current event status and get guidance")
    async def status(self, ctx: discord.ApplicationContext) -> None:
        """
        Check your current status in the event system and get helpful guidance
        on what commands you can use and where.
        """

        await ctx.defer(ephemeral=True)

        # Get user's active events
        user_events = await self._get_user_active_events(ctx.author.id)

        embed = discord.Embed(title="🎯 Your Loot Tracking Status", colour=0x00FF00 if user_events else 0xFFFF00)

        if user_events:
            # User is in events
            embed.description = f"✅ You're participating in **{len(user_events)}** active event(s)!"

            event_list = []
            for event in user_events[:5]:  # Show max 5 events
                try:
                    thread = await self.bot.fetch_channel(event["thread_id"])
                    event_list.append(f"🏆 **{event['name']}** - {thread.mention}")
                except Exception:
                    event_list.append(f"🏆 **{event['name']}** (Thread not found)")

            embed.add_field(name="📋 Your Active Events", value="\n".join(event_list), inline=False)

            embed.add_field(
                name="💡 What you can do:",
                value=(
                    "• Go to any of your event threads above\n"
                    "• Use `/event loot` to add items you've collected\n"
                    "• Use `/event finalise` to finalise an event you created"
                    "• Check the event card in the thread for current totals\n"
                ),
                inline=False,
            )
        else:
            # User not in any events
            embed.description = "⚠️ You're not participating in any active events."
            embed.colour = 0xFFFF00

            embed.add_field(
                name="🚀 How to get started:",
                value=(
                    f"**Option 1: Create a new event**\n"
                    f"• Use `/events create` in <#{CHANNEL_IDS[0]}>\n\n"
                    f"**Option 2: Join an existing event**\n"
                    f"• Use `/events join` from anywhere\n"
                    f"• Select from the dropdown of available events"
                ),
                inline=False,
            )

        # Add general help
        embed.add_field(name="❓ Need more help?", value="Use `/help` to see all available commands", inline=False)

        await ctx.followup.send(embed=embed, ephemeral=True)

    @event.command(description="Clean up orphaned event data in Redis")
    async def cleanup(self, ctx: discord.ApplicationContext) -> None:
        """Clean up orphaned event data where thread IDs don't match stored data."""

        await ctx.defer(ephemeral=True)

        try:
            # Get all event IDs
            event_ids = await self.bot.redis.smembers("qadir:events")
            logger.info(f"[CLEANUP] Found {len(event_ids)} Event IDs To Check")

            cleaned_count = 0
            kept_count = 0

            for event_id in list(event_ids):  # Convert to list to avoid modification during iteration
                event_id_str = str(event_id)
                logger.info(f"[CLEANUP] Checking Event {event_id_str}")

                # Try to get the event data
                event_data_raw = await self.bot.redis.get(f"qadir:event:{event_id_str}")

                if not event_data_raw:
                    # No data found, remove from events set
                    await self.bot.redis.srem("qadir:events", event_id)
                    logger.info(f"[CLEANUP] Removed Orphaned Event ID {event_id_str} From Events Set")
                    cleaned_count += 1
                else:
                    # Data exists, verify it's valid JSON
                    try:
                        event_data = json.loads(event_data_raw)
                        stored_thread_id = event_data.get("thread_id")

                        if str(stored_thread_id) != event_id_str:
                            logger.warning(f"[CLEANUP] Thread ID Mismatch: stored={stored_thread_id}, key={event_id_str}")
                            # Could fix this by updating the set, but for now just log it

                        logger.info(f"[CLEANUP] Event {event_id_str} Is Valid (name: {event_data.get('name')})")
                        kept_count += 1

                    except json.JSONDecodeError:
                        # Invalid JSON, remove both the hash and set entry
                        await self.bot.redis.delete(f"qadir:event:{event_id_str}")
                        await self.bot.redis.srem("qadir:events", event_id)
                        logger.info(f"[CLEANUP] Removed Corrupted Event Data For {event_id_str}")
                        cleaned_count += 1

            embed = SuccessEmbed(title="🧹 Redis Cleanup Results", description="Cleanup completed successfully!")
            embed.add_field(name="Events Kept", value=str(kept_count), inline=True)
            embed.add_field(name="Events Cleaned", value=str(cleaned_count), inline=True)

            await ctx.followup.send(embed=embed, ephemeral=True)
            logger.info(f"[CLEANUP] Completed: kept={kept_count}, cleaned={cleaned_count}")

        except Exception:
            logger.exception("[CLEANUP] Error During Cleanup")
            embed = discord.Embed(title="❌ Cleanup Failed", description="An error occurred during cleanup", colour=0xFF0000)
            await ctx.followup.send(embed=embed, ephemeral=True)


def setup(bot: Qadir) -> None:
    """
    Load the EventsCog into the bot.

    Args:
        bot (Qadir): The bot instance to load the cog into.
    """

    bot.add_cog(EventsCog(bot))
