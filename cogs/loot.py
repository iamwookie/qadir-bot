import json
import logging
from datetime import datetime, timezone
from collections import defaultdict

import discord

from config import config
from core import Cog, Qadir
from core.embeds import ErrorEmbed, SuccessEmbed
from modals import CreateEventModal, AddLootModal

GUILD_IDS: list[int] = config["loot"]["guilds"]
CHANNEL_IDS: list[int] = config["loot"]["channels"]

logger = logging.getLogger("qadir")


class EventSelectionView(discord.ui.View):
    """View for selecting events with dropdown."""

    def __init__(self, events: list, user_id: int, action: str):
        super().__init__(timeout=300)
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
                discord.SelectOption(
                    label=event["name"][:100], value=str(event["thread_id"]), description=description[:100], emoji=emoji  # Discord limit
                )
            )

        if options:
            select = EventSelect(
                options,
                self.action,
                disabled_values=(
                    [str(event["thread_id"]) for event in events if user_id in event["participants"]] if action == "join" else []
                ),
            )
            self.add_item(select)


class EventSelect(discord.ui.Select):
    """Dropdown for event selection."""

    def __init__(self, options: list, action: str, disabled_values: list = None):
        super().__init__(placeholder=f"Choose an event to {action}...", options=options, min_values=1, max_values=1)
        self.action = action
        self.disabled_values = disabled_values or []

    async def callback(self, interaction: discord.Interaction):
        selected_thread_id = int(self.values[0])

        # Disable already joined events for join action
        if self.action == "join" and str(selected_thread_id) in self.disabled_values:
            await interaction.response.send_message("❌ You're already a member of this event!", ephemeral=True)
            return

        # Get the loot cog instance
        loot_cog = interaction.client.get_cog("LootCog")

        if self.action == "join":
            await loot_cog._handle_join_event(interaction, selected_thread_id)
        elif self.action == "add_loot":
            await loot_cog._handle_add_loot(interaction, selected_thread_id)
        elif self.action == "summary":
            await loot_cog._handle_event_summary(interaction, selected_thread_id)


class LootCog(Cog, guild_ids=GUILD_IDS):
    """
    A cog to manage loot tracking events where participants can add items
    they've collected and see automatic distribution calculations.
    """

    async def _get_user_active_events(self, user_id: int) -> list:
        """Get list of active events that a user is participating in."""
        event_ids = await self.bot.redis.smembers("qadir:events")
        user_events = []

        for event_id in event_ids:
            event_data_raw = await self.bot.redis.hget(f"qadir:event:{event_id}", "data")
            if not event_data_raw:
                continue

            event_data = json.loads(event_data_raw)
            if event_data["status"] == "active" and user_id in event_data["participants"]:
                user_events.append(event_data)

        return user_events

    async def _update_event_card(self, event_data: dict) -> None:
        """Update the event card with current loot breakdown and distribution."""
        try:
            thread_id = int(event_data['thread_id'])
            message_id = int(event_data['message_id'])
            
            thread = await self.bot.fetch_channel(thread_id)
            message = await thread.fetch_message(message_id)
            
            # Get the original embed
            event_embed = message.embeds[0].copy()
            
            # Update basic stats
            participant_count = len(event_data['participants'])
            total_items = len(event_data['loot_items'])
            
            # Update the basic fields (Status, Participants, Total Items)
            event_embed.set_field_at(0, name="Status", value="🟢 Active" if event_data['status'] == 'active' else "🔴 Completed", inline=True)
            event_embed.set_field_at(1, name="Participants", value=str(participant_count), inline=True)
            event_embed.set_field_at(2, name="Total Items", value=str(total_items), inline=True)
            
            # Calculate loot breakdown and distribution
            if event_data['loot_items']:
                from collections import defaultdict
                
                # Group loot by type and by contributor
                loot_summary = defaultdict(int)
                loot_by_user = defaultdict(list)
                
                for item in event_data['loot_items']:
                    loot_summary[item['name']] += item['quantity']
                    try:
                        user = await self.bot.fetch_user(item['added_by'])
                        username = user.display_name
                    except:
                        username = f"User {item['added_by']}"
                    loot_by_user[username].append(f"{item['quantity']}x {item['name']}")
                
                # Create loot breakdown text
                breakdown_lines = []
                for username, items in sorted(loot_by_user.items()):
                    breakdown_lines.append(f"**{username}**: {', '.join(items)}")
                
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
                event_embed.set_field_at(3, name="🎁 Current Loot Breakdown", value=breakdown_text[:1024], inline=False)  # Discord field limit
                event_embed.set_field_at(4, name="⚖️ Distribution Preview", value=distribution_text[:1024], inline=False)
            else:
                # No loot yet
                event_embed.set_field_at(3, name="🎁 Current Loot Breakdown", value="*No loot added yet - use `/events add-loot` to contribute!*", inline=False)
                event_embed.set_field_at(4, name="⚖️ Distribution Preview", value="*Distribution will be calculated once loot is added*", inline=False)
            
            # Update the message
            await message.edit(embeds=[event_embed, message.embeds[1]])  # Keep the instructions embed
            logger.info(f"[EVENT-CARD] Successfully updated event card for {event_data['name']}")
            
        except Exception as e:
            logger.error(f"[EVENT-CARD] Failed to update event card: {e}")

    async def _get_all_active_events(self) -> list:
        """Get all active events."""
        try:
            logger.info("[REDIS] Getting all event IDs from qadir:events")
            event_ids = await self.bot.redis.smembers("qadir:events")
            logger.info(f"[REDIS] Found {len(event_ids)} event IDs: {list(event_ids)}")

            active_events = []

            for event_id in event_ids:
                logger.info(f"[REDIS] Fetching data for event {event_id} (type: {type(event_id)})")
                # Ensure event_id is a string for consistent key formatting
                event_id_str = str(event_id) if isinstance(event_id, int) else event_id
                event_data_raw = await self.bot.redis.hget(f"qadir:event:{event_id_str}", "data")

                if not event_data_raw:
                    logger.warning(f"[REDIS] No data found for event {event_id}")
                    continue

                try:
                    event_data = json.loads(event_data_raw)
                    logger.info(
                        f"[REDIS] Event {event_id}: name='{event_data.get('name')}', status='{event_data.get('status')}', participants={len(event_data.get('participants', []))}"
                    )

                    if event_data["status"] == "active":
                        active_events.append(event_data)
                        logger.info(f"[REDIS] Added active event {event_id} to results")
                    else:
                        logger.info(f"[REDIS] Skipping event {event_id} (status: {event_data['status']})")

                except json.JSONDecodeError as e:
                    logger.error(f"[REDIS] Failed to parse JSON for event {event_id}: {e}")
                    continue

            logger.info(f"[REDIS] Returning {len(active_events)} active events")
            return active_events

        except Exception as e:
            logger.error(f"[REDIS] Error in _get_all_active_events: {e}")
            return []

    async def _handle_join_event(self, interaction: discord.Interaction, thread_id: int):
        """Handle joining an event via dropdown selection."""
        event_data_raw = await self.bot.redis.hget(f"qadir:event:{thread_id}", "data")
        if not event_data_raw:
            await interaction.response.send_message("❌ Event not found.", ephemeral=True)
            return

        event_data = json.loads(event_data_raw)

        # Check if user is already a participant
        if interaction.user.id in event_data["participants"]:
            await interaction.response.send_message("✅ You're already participating in this event!", ephemeral=True)
            return

        # Add user to participants
        event_data["participants"].append(interaction.user.id)

        # Update Redis
        await self.bot.redis.hset(f"qadir:event:{thread_id}", "data", json.dumps(event_data))

        # Update the event card with new participant
        await self._update_event_card(event_data)

        await interaction.response.send_message(
            f"🎉 Successfully joined **{event_data['name']}**!\n" f"You can now add loot items to this event.", ephemeral=True
        )

    async def _handle_add_loot(self, interaction: discord.Interaction, thread_id: int):
        """Handle adding loot via dropdown selection."""
        event_data_raw = await self.bot.redis.hget(f"qadir:event:{thread_id}", "data")
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
        modal = AddLootModal(event_thread_id=thread_id, title=f"Add Loot to {event_data['name']}")
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
        Join an active event so you can add loot items and participate in distribution.
        Shows you a list of available events to join.
        """

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
            await ctx.respond(embed=embed, ephemeral=True)
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
            await ctx.respond(embed=embed, ephemeral=True)
            return

        # Show event selection
        embed = SuccessEmbed(title="🏆 Join an Event", description="Select an event to join from the dropdown below:")

        view = EventSelectionView(all_events, ctx.author.id, "join")
        await ctx.respond(embed=embed, view=view, ephemeral=True)

    @event.command(description="Add loot items you've collected to an event")
    async def add_loot(self, ctx: discord.ApplicationContext) -> None:
        """
        Add loot items you've collected to an event for distribution calculation.
        Shows you a list of events you're participating in to choose from.
        """

        await ctx.defer(ephemeral=True)

        # Get user's active events
        user_events = await self._get_user_active_events(ctx.author.id)

        if not user_events:
            embed = ErrorEmbed(
                title="❌ Not in Any Events",
                description=(
                    "You're not participating in any active events.\n\n"
                    "**To add loot, you need to:**\n"
                    "1. Use `/events join` to join an existing event\n"
                    "2. Or use `/events create` to create a new event\n\n"
                    f"**Create events in:** <#{CHANNEL_IDS[0]}>"
                ),
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return

        # Show event selection for adding loot
        embed = SuccessEmbed(title="🎒 Add Loot to Event", description="Select which event to add your loot items to:")

        view = EventSelectionView(user_events, ctx.author.id, "add_loot")
        await ctx.respond(embed=embed, view=view, ephemeral=True)

    @event.command(description="Show detailed summary of an event with loot distribution")
    async def summary(self, ctx: discord.ApplicationContext) -> None:
        """
        Show a comprehensive summary of an event including all participants,
        loot items, and automatic distribution calculations.
        """

        await ctx.defer(ephemeral=True)

        # Get all active events
        all_events = await self._get_all_active_events()

        if not all_events:
            embed = ErrorEmbed(title="❌ No Active Events", description="There are no active events to view summaries for.")
            await ctx.respond(embed=embed, ephemeral=True)
            return

        # If user is only in one event, show it directly
        if len(all_events) == 1:
            await self._handle_event_summary(ctx, all_events[0]["thread_id"])
            return

        # Show event selection for summary
        embed = SuccessEmbed(title="📊 View Event Summary", description="Select which event to view the summary for:")

        view = EventSelectionView(all_events, ctx.author.id, "summary")
        await ctx.respond(embed=embed, view=view, ephemeral=True)

    async def _handle_event_summary(self, interaction, thread_id: int):
        """Handle showing event summary via dropdown selection."""
        event_data_raw = await self.bot.redis.hget(f"qadir:event:{thread_id}", "data")
        if not event_data_raw:
            if hasattr(interaction, "response"):
                await interaction.response.send_message("❌ Event not found.", ephemeral=True)
            else:
                await interaction.respond("❌ Event not found.", ephemeral=True)
            return

        event_data = json.loads(event_data_raw)

        # Create summary embed
        embed = discord.Embed(
            title=f"📊 Event Summary: {event_data['name']}",
            description=event_data["description"],
            colour=0x00FF00 if event_data["status"] == "active" else 0xFF0000,
        )

        # Event info
        status_emoji = "🟢" if event_data["status"] == "active" else "🔴"
        embed.add_field(name="Status", value=f"{status_emoji} {event_data['status'].title()}", inline=True)
        embed.add_field(name="Participants", value=str(len(event_data["participants"])), inline=True)
        embed.add_field(name="Total Items", value=str(len(event_data["loot_items"])), inline=True)

        # Participants list
        participants = []
        for participant_id in event_data["participants"]:
            try:
                user = await self.bot.fetch_user(participant_id)
                participants.append(user.display_name)
            except:
                participants.append(f"User {participant_id}")

        embed.add_field(name="👥 Participants", value=", ".join(participants) if participants else "None", inline=False)

        # Loot items grouped by type
        if event_data["loot_items"]:
            loot_summary = defaultdict(int)
            loot_by_user = defaultdict(list)

            for item in event_data["loot_items"]:
                loot_summary[item["name"]] += item["quantity"]
                try:
                    user = await self.bot.fetch_user(item["added_by"])
                    username = user.display_name
                except:
                    username = f"User {item['added_by']}"
                loot_by_user[username].append(f"{item['quantity']}x {item['name']}")

            # Total loot summary
            loot_text = []
            for item_name, total_quantity in sorted(loot_summary.items()):
                per_person = total_quantity // len(event_data["participants"])
                remainder = total_quantity % len(event_data["participants"])

                if remainder > 0:
                    loot_text.append(f"**{total_quantity}x {item_name}** → {per_person} each + {remainder} extra")
                else:
                    loot_text.append(f"**{total_quantity}x {item_name}** → {per_person} each")

            embed.add_field(name="🎁 Loot Distribution", value="\n".join(loot_text) if loot_text else "No loot items yet", inline=False)

            # Individual contributions
            contrib_text = []
            for username, items in sorted(loot_by_user.items()):
                contrib_text.append(f"**{username}**: {', '.join(items)}")

            if contrib_text:
                embed.add_field(name="📝 Individual Contributions", value="\n".join(contrib_text), inline=False)
        else:
            embed.add_field(name="🎁 Loot Distribution", value="No loot items added yet", inline=False)

        # Event creator and creation time
        try:
            creator = await self.bot.fetch_user(event_data["creator_id"])
            embed.set_footer(text=f"Created by {creator.display_name}", icon_url=creator.display_avatar.url)
        except:
            embed.set_footer(text=f"Created by User {event_data['creator_id']}")

        created_at = datetime.fromisoformat(event_data["created_at"].replace("Z", "+00:00"))
        embed.timestamp = created_at

        if hasattr(interaction, "response"):
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.respond(embed=embed, ephemeral=True)

    @event.command(description="Close and finalize event with final distribution (event creator only)")
    async def finalize(self, ctx: discord.ApplicationContext) -> None:
        """
        Finalize the current event, lock the thread, and show final loot distribution.
        Only the event creator can use this command.
        """

        # Check if this is an event thread
        if not isinstance(ctx.channel, discord.Thread):
            embed = ErrorEmbed(description="This command can only be used in event threads.")
            await ctx.respond(embed=embed, ephemeral=True)
            return

        thread_id = ctx.channel.id
        event_data_raw = await self.bot.redis.hget(f"qadir:event:{thread_id}", "data")

        if not event_data_raw:
            embed = ErrorEmbed(description="This thread is not associated with an active event.")
            await ctx.respond(embed=embed, ephemeral=True)
            return

        event_data = json.loads(event_data_raw)

        # Check if user is the event creator
        creator_id = event_data['creator_id']
        current_user_id = ctx.author.id
        
        logger.info(f"[FINALIZE] Permission check: creator_id={creator_id} (type: {type(creator_id)}), current_user_id={current_user_id} (type: {type(current_user_id)})")
        
        if current_user_id != creator_id:
            embed = ErrorEmbed(
                title="❌ Permission Denied",
                description=f"Only the event creator can finalize the event.\n\nEvent creator: <@{creator_id}>\nYou are: <@{current_user_id}>"
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return

        # Check if event is already finalized
        if event_data["status"] != "active":
            embed = ErrorEmbed(description=f"This event is already {event_data['status']}.")
            await ctx.respond(embed=embed, ephemeral=True)
            return

        # Update event status
        event_data["status"] = "completed"
        event_data["finalized_at"] = datetime.now(timezone.utc).isoformat()

        # Update Redis
        await self.bot.redis.hset(f"qadir:event:{thread_id}", "data", json.dumps(event_data))

        # Update the event message
        try:
            message: discord.Message = await ctx.channel.fetch_message(event_data["message_id"])
            embed = message.embeds[0]
            embed.colour = 0xFF0000
            embed.set_field_at(0, name="Status", value="🔴 Completed", inline=True)
            await message.edit(embeds=message.embeds)
        except Exception:
            logger.exception(f"[LOOT] Failed to update event message for event {thread_id}")

        # Create dramatic finalization announcement
        if event_data['loot_items']:
            # Calculate final totals
            loot_summary = defaultdict(int)
            loot_by_user = defaultdict(list)
            
            for item in event_data['loot_items']:
                loot_summary[item['name']] += item['quantity']
                try:
                    user = await self.bot.fetch_user(item['added_by'])
                    username = user.display_name
                    user_mention = user.mention
                except:
                    username = f"User {item['added_by']}"
                    user_mention = f"<@{item['added_by']}>"
                loot_by_user[user_mention].append(f"{item['quantity']}x {item['name']}")

            # Create the main announcement embed
            final_embed = discord.Embed(
                title=f"🏁 EVENT FINALIZED: {event_data['name']}",
                description="The adventure has concluded! Here's what everyone contributed and earned:",
                colour=0xFFD700  # Gold color for dramatic effect
            )

            # Add contributions section with mentions
            if loot_by_user:
                contribution_lines = []
                for user_mention, items in sorted(loot_by_user.items()):
                    contribution_lines.append(f"{user_mention} contributed: **{', '.join(items)}**")
                
                final_embed.add_field(
                    name="🎒 Individual Contributions",
                    value="\n".join(contribution_lines),
                    inline=False
                )

            # Add distribution section with mentions for who gets what
            participant_mentions = []
            for participant_id in event_data['participants']:
                try:
                    user = await self.bot.fetch_user(participant_id)
                    participant_mentions.append(user.mention)
                except:
                    participant_mentions.append(f"<@{participant_id}>")

            distribution_lines = []
            individual_shares = []
            
            for item_name, total_quantity in sorted(loot_summary.items()):
                per_person = total_quantity // len(event_data['participants'])
                remainder = total_quantity % len(event_data['participants'])
                
                if per_person > 0:
                    if remainder > 0:
                        distribution_lines.append(f"**{total_quantity}x {item_name}** → {per_person} each + {remainder} extra")
                        individual_shares.append(f"• **{per_person}x {item_name}** each")
                    else:
                        distribution_lines.append(f"**{total_quantity}x {item_name}** → {per_person} each")
                        individual_shares.append(f"• **{per_person}x {item_name}** each")

            final_embed.add_field(
                name="⚖️ Final Distribution Breakdown",
                value="\n".join(distribution_lines),
                inline=False
            )

            # Add what each person gets
            if individual_shares:
                share_text = f"Each participant ({', '.join(participant_mentions)}) receives:\n" + "\n".join(individual_shares)
                final_embed.add_field(
                    name="🎁 Your Share",
                    value=share_text,
                    inline=False
                )

            final_embed.set_footer(text="Event has been locked. No more changes can be made.")
            final_embed.timestamp = datetime.now(timezone.utc)

            # Send to the thread
            await ctx.respond(embed=final_embed, ephemeral=False)
            
            # Also send a summary to the main channel
            try:
                main_channel = await self.bot.fetch_channel(CHANNEL_IDS[0])
                summary_embed = discord.Embed(
                    title=f"📢 Event Completed: {event_data['name']}",
                    description=f"Event has been finalized with {len(event_data['participants'])} participants and {len(event_data['loot_items'])} items!",
                    colour=0x00FF00
                )
                summary_embed.add_field(
                    name="Participants",
                    value=", ".join(participant_mentions),
                    inline=False
                )
                
                # Add top contributors
                if loot_by_user:
                    top_contributors = sorted(loot_by_user.items(), key=lambda x: len(x[1]), reverse=True)[:3]
                    contributor_text = []
                    for user_mention, items in top_contributors:
                        contributor_text.append(f"{user_mention}: {len(items)} items")
                    summary_embed.add_field(
                        name="Top Contributors",
                        value="\n".join(contributor_text),
                        inline=True
                    )
                
                await main_channel.send(embed=summary_embed)
                logger.info(f"[FINALIZE] Sent completion announcement to main channel for {event_data['name']}")
                
            except Exception as e:
                logger.error(f"[FINALIZE] Failed to send main channel announcement: {e}")
                
        else:
            await ctx.respond("🏁 Event finalized! No loot was collected during this event.", ephemeral=False)

        # Lock the thread
        await ctx.channel.edit(locked=True)

    @event.command(description="Show all events you've created or joined")
    async def list(self, ctx: discord.ApplicationContext) -> None:
        """
        Display a list of all loot tracking events you've created or are participating in,
        with their current status and basic statistics.
        """

        await ctx.defer(ephemeral=True)

        # Get all active events
        event_ids = await self.bot.redis.smembers("qadir:events")

        user_events = []
        participated_events = []

        for event_id in event_ids:
            event_data_raw = await self.bot.redis.hget(f"qadir:event:{event_id}", "data")
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

        await ctx.respond(embed=embed, ephemeral=True)

    @event.command(description="Check your current loot tracking status and get guidance")
    async def status(self, ctx: discord.ApplicationContext) -> None:
        """
        Check your current status in the loot tracking system and get helpful guidance
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
                except:
                    event_list.append(f"🏆 **{event['name']}** (Thread not found)")

            embed.add_field(name="📋 Your Active Events", value="\n".join(event_list), inline=False)

            embed.add_field(
                name="💡 What you can do:",
                value=(
                    "• Go to any of your event threads above\n"
                    "• Use `/add-loot` to add items you've collected\n"
                    "• Use `/event-summary` to see current totals\n"
                    "• Use `/finalize-event` if you created the event"
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

        await ctx.respond(embed=embed, ephemeral=True)

    @event.command(description="Debug: Check Redis event storage")
    async def debug(self, ctx: discord.ApplicationContext) -> None:
        """Debug command to check what events are stored in Redis."""
        await ctx.defer(ephemeral=True)

        # Get all event IDs from Redis
        event_ids = await self.bot.redis.smembers("qadir:events")

        debug_info = []
        debug_info.append(f"**Found {len(event_ids)} event IDs in Redis:**")

        for event_id in event_ids:
            debug_info.append(f"- Event ID: `{event_id}` (type: {type(event_id)})")

            # Try to get event data
            event_data_raw = await self.bot.redis.hget(f"qadir:event:{event_id}", "data")
            if event_data_raw:
                try:
                    event_data = json.loads(event_data_raw)
                    debug_info.append(f"  - Name: {event_data.get('name', 'Unknown')}")
                    debug_info.append(f"  - Status: {event_data.get('status', 'Unknown')}")
                    debug_info.append(f"  - Participants: {len(event_data.get('participants', []))}")
                except Exception as e:
                    debug_info.append(f"  - Error parsing data: {e}")
            else:
                debug_info.append(f"  - No data found for this ID")

        embed = discord.Embed(title="🔍 Redis Debug Info", description="\n".join(debug_info), colour=0xFF0000)

        await ctx.respond(embed=embed, ephemeral=True)

    @event.command(description="Test Redis connection and basic operations")
    async def test_redis(self, ctx: discord.ApplicationContext) -> None:
        """Test Redis connection and basic operations."""
        await ctx.defer(ephemeral=True)

        test_results = []
        all_passed = True

        try:
            # Test 1: Basic connection
            test_results.append("**🔌 Connection Test:**")
            await self.bot.redis.ping()
            test_results.append("✅ Redis connection successful")
            logger.info("[REDIS-TEST] Connection test passed")
        except Exception as e:
            test_results.append(f"❌ Redis connection failed: {e}")
            logger.error(f"[REDIS-TEST] Connection test failed: {e}")
            all_passed = False

        try:
            # Test 2: Write operation
            test_results.append("\n**✏️ Write Test:**")
            test_key = "qadir:test:write"
            test_value = f"test_value_{datetime.now(timezone.utc).timestamp()}"
            await self.bot.redis.set(test_key, test_value)
            test_results.append(f"✅ Successfully wrote test data")
            logger.info(f"[REDIS-TEST] Write test passed: {test_key} = {test_value}")
        except Exception as e:
            test_results.append(f"❌ Write test failed: {e}")
            logger.error(f"[REDIS-TEST] Write test failed: {e}")
            all_passed = False

        try:
            # Test 3: Read operation
            test_results.append("\n**📖 Read Test:**")
            retrieved_value = await self.bot.redis.get(test_key)
            if retrieved_value == test_value:
                test_results.append("✅ Successfully read test data")
                logger.info(f"[REDIS-TEST] Read test passed: retrieved {retrieved_value}")
            else:
                test_results.append(f"❌ Read test failed: expected {test_value}, got {retrieved_value}")
                logger.error(f"[REDIS-TEST] Read test failed: expected {test_value}, got {retrieved_value}")
                all_passed = False
        except Exception as e:
            test_results.append(f"❌ Read test failed: {e}")
            logger.error(f"[REDIS-TEST] Read test failed: {e}")
            all_passed = False

        try:
            # Test 4: Set operations (used for events list)
            test_results.append("\n**📝 Set Operations Test:**")
            test_set_key = "qadir:test:set"
            await self.bot.redis.sadd(test_set_key, "item1", "item2", "item3")
            set_members = await self.bot.redis.smembers(test_set_key)
            if len(set_members) == 3:
                test_results.append("✅ Set operations working correctly")
                logger.info(f"[REDIS-TEST] Set operations test passed: {set_members}")
            else:
                test_results.append(f"❌ Set operations failed: expected 3 items, got {len(set_members)}")
                logger.error(f"[REDIS-TEST] Set operations test failed: {set_members}")
                all_passed = False
        except Exception as e:
            test_results.append(f"❌ Set operations test failed: {e}")
            logger.error(f"[REDIS-TEST] Set operations test failed: {e}")
            all_passed = False

        try:
            # Test 5: Hash operations (used for event data)
            test_results.append("\n**🗂️ Hash Operations Test:**")
            test_hash_key = "qadir:test:hash"
            await self.bot.redis.hset(test_hash_key, "field1", "value1")
            await self.bot.redis.hset(test_hash_key, "field2", "value2")
            retrieved_hash = await self.bot.redis.hget(test_hash_key, "field1")
            if retrieved_hash == "value1":
                test_results.append("✅ Hash operations working correctly")
                logger.info(f"[REDIS-TEST] Hash operations test passed")
            else:
                test_results.append(f"❌ Hash operations failed: expected 'value1', got {retrieved_hash}")
                logger.error(f"[REDIS-TEST] Hash operations test failed: {retrieved_hash}")
                all_passed = False
        except Exception as e:
            test_results.append(f"❌ Hash operations test failed: {e}")
            logger.error(f"[REDIS-TEST] Hash operations test failed: {e}")
            all_passed = False

        try:
            # Cleanup test data
            test_results.append("\n**🧹 Cleanup:**")
            await self.bot.redis.delete(test_key, test_set_key, test_hash_key)
            test_results.append("✅ Test data cleaned up")
            logger.info("[REDIS-TEST] Cleanup completed")
        except Exception as e:
            test_results.append(f"⚠️ Cleanup warning: {e}")
            logger.warning(f"[REDIS-TEST] Cleanup warning: {e}")

        # Create result embed
        embed = discord.Embed(
            title="🔍 Redis Connection Test Results", description="\n".join(test_results), colour=0x00FF00 if all_passed else 0xFF0000
        )

        if all_passed:
            embed.add_field(
                name="✅ Overall Result", value="All Redis tests passed! The database connection is working properly.", inline=False
            )
        else:
            embed.add_field(
                name="❌ Overall Result", value="Some Redis tests failed. Check the logs for detailed error information.", inline=False
            )

        await ctx.respond(embed=embed, ephemeral=True)

    @event.command(description="Clean up orphaned event data in Redis")
    async def cleanup(self, ctx: discord.ApplicationContext) -> None:
        """Clean up orphaned event data where thread IDs don't match stored data."""
        await ctx.defer(ephemeral=True)

        try:
            # Get all event IDs
            event_ids = await self.bot.redis.smembers("qadir:events")
            logger.info(f"[CLEANUP] Found {len(event_ids)} event IDs to check")

            cleaned_count = 0
            kept_count = 0

            for event_id in list(event_ids):  # Convert to list to avoid modification during iteration
                event_id_str = str(event_id)
                logger.info(f"[CLEANUP] Checking event {event_id_str}")

                # Try to get the event data
                event_data_raw = await self.bot.redis.hget(f"qadir:event:{event_id_str}", "data")

                if not event_data_raw:
                    # No data found, remove from events set
                    await self.bot.redis.srem("qadir:events", event_id)
                    logger.info(f"[CLEANUP] Removed orphaned event ID {event_id_str} from events set")
                    cleaned_count += 1
                else:
                    # Data exists, verify it's valid JSON
                    try:
                        event_data = json.loads(event_data_raw)
                        stored_thread_id = event_data.get("thread_id")

                        if str(stored_thread_id) != event_id_str:
                            logger.warning(f"[CLEANUP] Thread ID mismatch: stored={stored_thread_id}, key={event_id_str}")
                            # Could fix this by updating the set, but for now just log it

                        logger.info(f"[CLEANUP] Event {event_id_str} is valid (name: {event_data.get('name')})")
                        kept_count += 1

                    except json.JSONDecodeError:
                        # Invalid JSON, remove both the hash and set entry
                        await self.bot.redis.delete(f"qadir:event:{event_id_str}")
                        await self.bot.redis.srem("qadir:events", event_id)
                        logger.info(f"[CLEANUP] Removed corrupted event data for {event_id_str}")
                        cleaned_count += 1

            embed = SuccessEmbed(title="🧹 Redis Cleanup Results", description=f"Cleanup completed successfully!")
            embed.add_field(name="Events Kept", value=str(kept_count), inline=True)
            embed.add_field(name="Events Cleaned", value=str(cleaned_count), inline=True)

            await ctx.respond(embed=embed, ephemeral=True)
            logger.info(f"[CLEANUP] Completed: kept={kept_count}, cleaned={cleaned_count}")

        except Exception as e:
            logger.error(f"[CLEANUP] Error during cleanup: {e}")
            embed = discord.Embed(title="❌ Cleanup Failed", description=f"An error occurred during cleanup: {e}", colour=0xFF0000)
            await ctx.respond(embed=embed, ephemeral=True)



def setup(bot: Qadir) -> None:
    """
    Load the LootCog into the bot.

    :param bot: The Qadir instance
    """

    bot.add_cog(LootCog(bot))
