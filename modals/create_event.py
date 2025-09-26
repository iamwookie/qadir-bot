import json
import logging
from datetime import datetime, timezone
from enum import Enum

import discord

from core import Qadir
from core.embeds import ErrorEmbed, SuccessEmbed

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

        channel = interaction.channel

        if not isinstance(channel, discord.TextChannel):
            embed = ErrorEmbed(title="⚠️ Invalid Channel", description="Please use this command in a text channel.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        event_name = self.children[0].value
        description = self.children[1].value

        # Create thread for the event
        thread_title = f"🏆 {event_name}"
        thread = await channel.create_thread(name=thread_title, type=discord.ChannelType.public_thread)

        # Create event embed
        event_embed = SuccessEmbed(title=f"📅 Event: {event_name}", description=description)
        event_embed.add_field(name="Status", value="🟢 Active", inline=True)
        event_embed.add_field(name="Participants", value="1", inline=True)
        event_embed.add_field(name="Total Items", value="0", inline=True)

        # Add participant list
        event_embed.add_field(name="👥 Participants", value=interaction.user.display_name, inline=False)

        # Add loot breakdown section (initially empty)
        event_embed.add_field(name="🎁 Loot Breakdown", value="*No loot added yet - use `/event loot` to contribute!*", inline=False)

        # Add distribution preview (initially empty)
        event_embed.add_field(name="⚖️ Distribution Preview", value="*Distribution will be calculated once loot is added.*", inline=False)

        event_embed.set_footer(text=f"Created by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        event_embed.timestamp = datetime.now(timezone.utc)

        # Instructions embed
        instructions_embed = discord.Embed(
            title="📋 How to participate:",
            description=(
                "• Check the event card above for current totals and distribution\n"
                "• Use `/event join` to join this event\n"
                "• Use `/event loot` to add items you've collected\n"
                "• Event creator can use `/event finalize` to finalise the event"
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
            logger.info(f"[REDIS] Storing Event Data For Thread {thread.id}")
            logger.info(f"[REDIS] Event Data: {json.dumps(event_data, indent=2)}")

            # Store event data
            await client.redis.set(f"qadir:event:{thread_id_str}", json.dumps(event_data))
            logger.info(f"[REDIS] Successfully Stored Event Data For Thread {thread_id_str}")

            # Add to events set
            await client.redis.sadd("qadir:events", thread_id_str)
            logger.info(f"[REDIS] Successfully Added Thread {thread_id_str} To Events Set")

            # Verify the data was stored
            stored_data = await client.redis.get(f"qadir:event:{thread_id_str}")
            if stored_data:
                logger.info(f"[REDIS] Verification: Successfully Retrieved Stored Data For Thread: {thread_id_str}")
                # Double-check the thread_id in the stored data matches
                try:
                    verified_data = json.loads(stored_data)
                    stored_thread_id = verified_data.get("thread_id")
                    if stored_thread_id == thread_id_str:
                        logger.info(f"[REDIS] Thread ID Consistency Verified: {stored_thread_id}")
                    else:
                        logger.error(f"[REDIS] Thread ID Mismatch: key={thread_id_str}, stored={stored_thread_id}")
                except Exception:
                    logger.exception("[REDIS] Failed To Verify Stored Data")
            else:
                logger.error(f"[REDIS] Verification Failed: Could Not Retrieve Stored Data For Thread: {thread_id_str}")

        except Exception:
            logger.exception(f"[REDIS] Failed To Store Event Data For Thread: {thread_id_str}")
            embed = ErrorEmbed(
                title="⚠️ Database Error",
                description=f"Event **{event_name}** was created but there was an issue saving to database. Please contact an admin.",
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        embed = SuccessEmbed(
            description=f"Event **{event_name}** has been created in {thread.mention}!\nYou've been automatically added as a participant.",
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
