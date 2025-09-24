import json
import logging
from datetime import datetime, timezone
from enum import Enum

import discord

from config import config
from core import Qadir
from core.embeds import SuccessEmbed, ErrorEmbed

CHANNEL_ID: int = config["loot"]["channels"][0]

logger = logging.getLogger("qadir")


class EventStatus(Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class CreateEventModal(discord.ui.Modal):
    """Modal for creating a loot tracking event."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.add_item(discord.ui.InputText(label="Event Name", style=discord.InputTextStyle.short, required=True))
        self.add_item(discord.ui.InputText(label="Description", style=discord.InputTextStyle.long, required=False))

    async def on_error(self, _: discord.Interaction, error: Exception) -> None:
        logger.error("[MODAL] CreateEventModal Error", exc_info=error)

    async def callback(self, interaction: discord.Interaction):
        """Handle the modal submission and create an event thread."""

        await interaction.response.defer(ephemeral=True)

        channel: discord.TextChannel = await interaction.client.fetch_channel(CHANNEL_ID)

        event_name = self.children[0].value
        description = self.children[1].value

        # Create thread for the event
        thread_title = f"🏆 {event_name}"
        thread = await channel.create_thread(name=thread_title, type=discord.ChannelType.public_thread)

        # Create event embed
        event_embed = SuccessEmbed(title=f"📅 Event: {event_name}", description=description)
        event_embed.add_field(name="Status", value="🟢 Active", inline=True)
        event_embed.add_field(name="Participants", value="1", inline=True)
        event_embed.add_field(name="Total Loot Items", value="0", inline=True)
        event_embed.set_footer(text=f"Created by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        event_embed.timestamp = datetime.now(timezone.utc)

        # Instructions embed
        instructions_embed = discord.Embed(
            title="📋 How to participate:",
            description=(
                "• Use `/join-event` to join this event\n"
                "• Use `/add-loot` to add items you've collected\n"
                "• Use `/event-summary` to see current totals\n"
                "• Event creator can use `/finalize-event` to close and distribute loot"
            ),
            colour=0x0099FF,
        )

        message = await thread.send(embeds=[event_embed, instructions_embed])

        client: Qadir = interaction.client

        # Store event data in Redis
        thread_id_str = str(thread.id)
        message_id_str = str(message.id)
        user_id = interaction.user.id

        event_data = {
            "thread_id": thread_id_str,
            "message_id": message_id_str,
            "name": event_name,
            "description": description,
            "creator_id": user_id,
            "status": EventStatus.ACTIVE.value,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "participants": [user_id],  # Creator is automatically a participant
            "loot_items": [],
        }

        try:
            logger.info(f"[REDIS] Storing event data for thread {thread.id}")
            logger.info(f"[REDIS] Event data: {json.dumps(event_data, indent=2)}")

            # Store event data
            await client.redis.hset(f"qadir:event:{thread_id_str}", "data", json.dumps(event_data))
            logger.info(f"[REDIS] Successfully stored event data for thread {thread_id_str}")

            # Add to events set
            await client.redis.sadd("qadir:events", thread_id_str)
            logger.info(f"[REDIS] Successfully added thread {thread_id_str} to events set")

            # Verify the data was stored
            stored_data = await client.redis.hget(f"qadir:event:{thread_id_str}", "data")
            if stored_data:
                logger.info(f"[REDIS] Verification: Successfully retrieved stored data for thread {thread_id_str}")
                # Double-check the thread_id in the stored data matches
                try:
                    verified_data = json.loads(stored_data)
                    stored_thread_id = verified_data.get("thread_id")
                    if stored_thread_id == thread_id_str:
                        logger.info(f"[REDIS] Thread ID consistency verified: {stored_thread_id}")
                    else:
                        logger.error(f"[REDIS] Thread ID MISMATCH: key={thread_id_str}, stored={stored_thread_id}")
                except Exception as parse_error:
                    logger.error(f"[REDIS] Failed to verify stored data: {parse_error}")
            else:
                logger.error(f"[REDIS] Verification FAILED: Could not retrieve stored data for thread {thread_id_str}")

        except Exception as e:
            logger.error(f"[REDIS] Failed to store event data for thread {thread_id_str}: {e}")
            embed = ErrorEmbed(
                title="⚠️ Database Error",
                description=f"Event **{event_name}** was created but there was an issue saving to database. Please contact an admin.",
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        embed = SuccessEmbed(
            title="✅ Event Created Successfully!",
            description=f"Event **{event_name}** has been created in {thread.mention}!\nYou've been automatically added as a participant.",
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
