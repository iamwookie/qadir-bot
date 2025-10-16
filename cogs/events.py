import json
import logging

import discord

from config import config
from core import Cog, Qadir
from models.events import Event, LootItem
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

    async def get_or_fetch_event_by_id(self, thread_id: int) -> Event | None:
        """
        Fetch event data by thread ID. Uses cache if available.

        Args:
            thread_id (int): The Discord thread ID of the event.
        Returns:
            An Event object, or None.
        """

        try:
            cached = await self.redis.get(f"{self.REDIS_PREFIX}:{str(thread_id)}")
            if cached:
                return Event(**json.loads(cached))

            event = await Event.find_one(Event.thread_id == str(thread_id))
            if event:
                await self.redis.set(
                    f"{self.REDIS_PREFIX}:{str(thread_id)}", json.dumps(event.model_dump(), default=str), ex=self.REDIS_TTL
                )
                return event

            return None
        except Exception:
            logger.exception(f"[EVENTS] Error Fetching Event By ID: {thread_id}")
            return None

    async def update_event_card(self, event: Event) -> None:
        """Update an event card with current loot breakdown and distribution.

        Args:
            event (Event): The event object to update the card with.
        """

        try:
            message_id = int(event.message_id)
            thread_id = int(event.thread_id)

            # Get or fetch the message
            message = self.bot.get_message(message_id)
            if not message:
                thread = self.bot.get_channel(thread_id)
                if not thread:
                    thread = await self.bot.fetch_channel(thread_id)

                message = await thread.fetch_message(message_id)

            # Create new embed with fresh data
            event_embed = EventEmbed(
                name=event.name,
                desc=event.description,
                status=event.status,
                participants=event.participants,
                loot_entries=event.loot_entries,
            )

            creator_id = event.creator_id
            creator = self.bot.get_user(int(creator_id))
            if not creator:
                creator = await self.bot.fetch_user(int(creator_id))

            event_embed.set_footer(text=f"Created by {creator}", icon_url=creator.display_avatar.url)

            # Update the message
            await message.edit(embeds=[event_embed, message.embeds[1]])  # Keep the instructions embed

            logger.info(f"[EVENTS] Updated Event Card For: {thread_id} ({event.name})")
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

            event = await self.get_or_fetch_event_by_id(ctx.channel.id)
            if event:
                # Check if user is already a participant in this event
                if str(ctx.author.id) in event.participants:
                    embed = SuccessEmbed(
                        title="Already Participating",
                        description=(
                            f"You're already participating in **{event.name}**!\n\n"
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
                    event.participants.append(str(ctx.author.id))
                    await event.replace()

                    # Invalidate cache
                    await self.redis.delete(f"{self.REDIS_PREFIX}:{thread_id}")

                    # Update the event card with the new participant
                    await self.update_event_card(event)

                    embed = SuccessEmbed(
                        title="🎉 Successfully Joined Event!",
                        description=(
                            f"Welcome to **{event.name}**!\n\n"
                            f"**You can now:**\n"
                            f"• Use `/event loot` in this thread to add items\n"
                            f"• Check the event card above for current totals"
                        ),
                    )
                    await ctx.followup.send(embed=embed, ephemeral=True)
                    return

        await ctx.defer(ephemeral=True)

        # Fetch active events
        active_events = await Event.find(Event.status == EventStatus.ACTIVE).to_list()
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
        joinable_events = [event for event in active_events if str(ctx.author.id) not in event.participants]

        if not joinable_events:
            # User is already in all events
            user_events = [event for event in active_events if str(ctx.author.id) in event.participants]
            event_list = "\n".join([f"• 🏆 **{event.name}**" for event in user_events])

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
        event = await self.get_or_fetch_event_by_id(thread_id)
        if not event:
            await ctx.respond(embed=thread_error_embed, ephemeral=True)
            return

        # Check if user is a participant
        if str(ctx.author.id) not in event.participants:
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

        items = [LootItem(**item) for item in json.loads(items_data)]

        # Show the AddLootModal
        modal = AddLootModal(self, event, items)
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
        event = await self.get_or_fetch_event_by_id(thread_id)
        if not event:
            embed = ErrorEmbed(None, "This thread is not associated with an active event.")
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        # Check if user is the event creator
        creator_id = event.creator_id
        current_user_id = str(ctx.author.id)

        if current_user_id != creator_id:
            embed = ErrorEmbed(
                "Permission Denied",
                f"Only the event creator can finalise the event.\n\nEvent creator: <@{creator_id}>\nYou are: <@{current_user_id}>",
            )
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        # Check if event is already finalised
        if event.status != EventStatus.ACTIVE:
            embed = ErrorEmbed(None, "This event is already finalised.")
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        # Update event status
        event.status = EventStatus.COMPLETED
        await event.replace()

        # Invalidate cache
        await self.redis.delete(f"{self.REDIS_PREFIX}:{thread_id}")

        # Update the event card to show it's finalised
        await self.update_event_card(event)

        # Send confirmation
        final_embed = discord.Embed(
            title="Event Finalised",
            description=f"""**{event.name}** has concluded.
            A summary can be found in {ctx.channel.mention}.""",
            colour=0xFFD700,
        )
        final_embed.set_footer(text="The event has been locked. No more changes can be made")
        await ctx.followup.send(embed=final_embed, ephemeral=True)

        # Lock the thread to prevent further messages
        await ctx.channel.edit(locked=True)

    @event.command(description="Show all events you've created")
    async def list(self, ctx: discord.ApplicationContext) -> None:
        """
        Lists all active events that the user has created.

        Args:
            ctx (discord.ApplicationContext): The context of the command invocation.
        Returns:
            None
        """

        await ctx.defer(ephemeral=True)

        # Get all active events for the user
        events = await Event.find(Event.creator_id == str(ctx.author.id)).to_list()
        if not events:
            embed = ErrorEmbed(None, "You haven't created any active events.")
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        embed = SuccessEmbed(title="Your Events", description="A summary of the events you've created.")

        created_text: list[str] = []
        for event in events:
            status_emoji = "🟢" if event.status == EventStatus.ACTIVE else "🔴"
            created_text.append(
                f"{status_emoji} **{event.name}** (`{len(event.participants)}` participant(s), `{len(event.loot_entries)}` item(s))"
            )

        embed.description = "\n".join(created_text)

        await ctx.followup.send(embed=embed, ephemeral=True)


def setup(bot: Qadir) -> None:
    """
    Load the EventsCog into the bot.

    Args:
        bot (Qadir): The bot instance to load the cog into.
    """

    bot.add_cog(EventsCog(bot))
