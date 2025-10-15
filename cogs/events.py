import json
import logging
from collections import defaultdict

import discord
from pymongo import ReturnDocument

from config import config
from core import Cog, Qadir
from utils.embeds import ErrorEmbed, EventEmbed, SuccessEmbed
from utils.enums import EventStatus
from utils.modals import AddLootModal, CreateEventModal
from utils.views import EventSelectionView

GUILD_IDS = config["events"]["guilds"]
CHANNEL_IDS = config["events"]["channels"]

logger = logging.getLogger("qadir")


class EventsCog(Cog, name="Events", guild_ids=GUILD_IDS):
    """
    A cog to manage loot tracking events which can be used for efficient loot distribution.
    """

    REDIS_PREFIX: str = "qadir:events"
    REDIS_TTL: int = 3600  # seconds

    def __init__(self, bot):
        """
        Initialize the cog.

        Args:
            bot (Qadir): The bot instance to load the cog into
        """

        super().__init__(bot)

        # MongoDB collection wrapper
        self.db = self.bot.db["events"]

    async def fetch_active_events(self) -> list | None:
        """
        Fetch all active events.

        Returns:
            A list of active event dictionaries, or None.
        """

        try:
            active_events = await self.db.find({"status": "active"}).to_list()
            return active_events if active_events else None
        except Exception:
            logger.exception("[EVENTS] Error Fetching Active Events")
            return None

    async def fetch_user_active_events(self, user_id: int) -> list | None:
        """
        Fetch a list of active events that a user is participating in.

        Args:
            user_id (int): The Discord user ID to check for active events.
        Returns:
            A list of active event dictionaries that the user participates in, or None.
        """

        try:
            active_events = await self.db.find({"participants": str(user_id), "status": "active"}).to_list()
            return active_events if active_events else None
        except Exception:
            logger.exception(f"[EVENTS] Error Fetching Active Events For User: {user_id}")
            return None

    async def get_or_fetch_event_by_id(self, thread_id: int) -> dict | None:
        """
        Fetch event data by thread ID. Uses cache if available.

        Args:
            thread_id (int): The Discord thread ID of the event.
        Returns:
            A dictionary of the event data, or None.
        """

        try:
            cache_data = await self.redis.get(f"{self.REDIS_PREFIX}:{str(thread_id)}")
            if cache_data:
                return json.loads(cache_data)

            event_data = await self.db.find_one({"thread_id": str(thread_id)})
            if event_data:
                await self.redis.set(f"{self.REDIS_PREFIX}:{str(thread_id)}", json.dumps(event_data, default=str), ex=self.REDIS_TTL)
                return event_data

            return None
        except Exception:
            logger.exception(f"[EVENTS] Error Fetching Event By ID: {thread_id}")
            return None

    async def update_event_card(self, event_data: dict) -> None:
        """Update an event card with current loot breakdown and distribution.

        Args:
            event_data (dict): The event data to update the card with.
        """

        try:
            message_id = int(event_data["message_id"])
            thread_id = int(event_data["thread_id"])

            # Get or fetch the message
            message = self.bot.get_message(message_id)
            if not message:
                thread = self.bot.get_channel(thread_id)
                if not thread:
                    thread = await self.bot.fetch_channel(thread_id)

                message = await thread.fetch_message(message_id)

            # Create new embed with fresh data
            event_embed = EventEmbed(
                name=event_data["name"],
                description=event_data["description"],
                status=event_data["status"],
                participants=event_data["participants"],
                loot_entries=event_data["loot_entries"],
            )

            creator_id = event_data["creator_id"]
            creator = self.bot.get_user(int(creator_id))
            if not creator:
                creator = await self.bot.fetch_user(int(creator_id))

            event_embed.set_footer(text=f"Created by {creator}", icon_url=creator.display_avatar.url)

            # Update the message
            await message.edit(embeds=[event_embed, message.embeds[1]])  # Keep the instructions embed

            logger.info(f"[EVENTS] Updated Event Card For: {thread_id} ({event_data['name']})")
        except Exception:
            logger.exception("[EVENTS] Failed To Update Event Card")

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
            embed = ErrorEmbed(None, f"This command can only be used in: {', '.join(allowed_channels)}")
            await ctx.respond(embed=embed, ephemeral=True)
            return

        modal = CreateEventModal(self, title="Create Loot Event")
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

            event_data = await self.get_or_fetch_event_by_id(ctx.channel.id)
            if event_data:
                # Check if user is already a participant in this event
                if str(ctx.author.id) in event_data["participants"]:
                    embed = SuccessEmbed(
                        title="Already Participating",
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
                    event_data = await self.db.find_one_and_update(
                        {"thread_id": str(thread_id)},
                        {"$addToSet": {"participants": str(ctx.author.id)}},
                        return_document=ReturnDocument.AFTER,
                    )

                    # Invalidate cache
                    await self.redis.delete(f"{self.REDIS_PREFIX}:{thread_id}")

                    # Update the event card with the new participant
                    await self.update_event_card(event_data)

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

        # Fetch active events
        active_events = await self.fetch_active_events()

        if not active_events:
            embed = ErrorEmbed(
                "No Active Events",
                (
                    "There are no active events to join right now.\n\n"
                    "**Want to create an event?**\n"
                    f"Use `/event create` in <#{CHANNEL_IDS[0]}>"
                ),
            )
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        # Filter events user can join (not already a member of)
        joinable_events = [event for event in active_events if str(ctx.author.id) not in event["participants"]]

        if not joinable_events:
            # User is already in all events
            user_events = [event for event in active_events if str(ctx.author.id) in event["participants"]]
            event_list = "\n".join([f"• 🏆 **{event['name']}**" for event in user_events])

            embed = SuccessEmbed(
                title="Already Participating", description=f"You're already participating in all active events:\n\n{event_list}"
            )
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        # Show event selection
        embed = SuccessEmbed(title="🏆 Join an Event", description="Select an event to join from the dropdown below:")

        view = EventSelectionView(self, active_events, ctx.author.id)
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
            "Not In Event Thread",
            (
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
        event_data = await self.get_or_fetch_event_by_id(thread_id)
        if not event_data:
            await ctx.respond(embed=thread_error_embed, ephemeral=True)
            return

        # Check if user is a participant
        if str(ctx.author.id) not in event_data["participants"]:
            embed = ErrorEmbed(
                "Not Participating", ("You must join this event before adding loot.\n" "Use `/event join` to join this event.")
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return

        # Fetch available items
        # NOTE: Move to database eventually
        items_data = await self.redis.get(f"{self.REDIS_PREFIX}:items")

        if not items_data:
            embed = ErrorEmbed("No Items Configured", "No items are configured for loot tracking. Please contact an administrator.")
            await ctx.respond(embed=embed, ephemeral=True)
            return

        items_data = json.loads(items_data)

        # Show the AddLootModal
        modal = AddLootModal(self, thread_id, event_data, items_data)
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
            embed = ErrorEmbed(None, "This command can only be used in event threads.")
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        thread_id = ctx.channel.id
        event_data = await self.get_or_fetch_event_by_id(thread_id)
        if not event_data:
            embed = ErrorEmbed(None, "This thread is not associated with an active event.")
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        # Check if user is the event creator
        creator_id = event_data["creator_id"]
        current_user_id = str(ctx.author.id)

        if current_user_id != creator_id:
            embed = ErrorEmbed(
                "Permission Denied",
                f"Only the event creator can finalise the event.\n\nEvent creator: <@{creator_id}>\nYou are: <@{current_user_id}>",
            )
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        # Check if event is already finalised
        if event_data["status"] != EventStatus.ACTIVE.value:
            embed = ErrorEmbed(None, "This event is already finalised.")
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        # Update event status
        await self.db.update_one(
            {"thread_id": str(thread_id)}, {"$set": {"status": EventStatus.COMPLETED.value, "completed_at": discord.utils.utcnow()}}
        )

        # Invalidate cache
        await self.redis.delete(f"{self.REDIS_PREFIX}:{thread_id}")

        # Update the event message
        try:
            message = await ctx.channel.fetch_message(event_data["message_id"])
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
                    user = self.bot.get_user(int(user_id))
                    if not user:
                        user = await self.bot.fetch_user(int(user_id))
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
            final_embed.timestamp = discord.utils.utcnow()

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
        active_events = await self.fetch_user_active_events(ctx.author.id)
        if not active_events:
            embed = ErrorEmbed(None, "You haven't created or joined any active events.")
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        user_events = []
        participated_events = []

        for event in active_events:
            if event["creator_id"] == str(ctx.author.id):
                user_events.append(event)
            elif str(ctx.author.id) in event["participants"]:
                participated_events.append(event)

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

        await ctx.followup.send(embed=embed, ephemeral=True)


def setup(bot: Qadir) -> None:
    """
    Load the EventsCog into the bot.

    Args:
        bot (Qadir): The bot instance to load the cog into.
    """

    bot.add_cog(EventsCog(bot))
