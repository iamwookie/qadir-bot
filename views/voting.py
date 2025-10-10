import discord
import json

import logging

from core import Qadir
from core.embeds import SuccessEmbed, ErrorEmbed
from typing import TypedDict

logger = logging.getLogger("qadir")


class Votes(TypedDict):
    upvotes: set[int]
    downvotes: set[int]


class VotingView(discord.ui.View):
    """
    A view for voting that uses buttons instead of reactions.
    """

    def __init__(self, thread_id: int = None, message_id: int = None) -> None:
        super().__init__(timeout=None)

        self.thread_id = thread_id
        self.message_id = message_id
        self.votes: Votes | None = None

    async def on_error(self, error, _: discord.ui.Item, interaction: discord.Interaction) -> None:
        logger.error(f"[VOTING] VotingView Error", exc_info=error)
        await interaction.response.send_message(embed=ErrorEmbed(), ephemeral=True)

    async def _fetch_votes(self, bot: Qadir):
        """Fetch current votes from Redis."""

        proposal_data_raw = await bot.redis.get(f"qadir:proposal:{self.thread_id}")

        if proposal_data_raw:
            proposal_data = json.loads(proposal_data_raw)

            self.votes: Votes = {
                "upvotes": set(proposal_data.get("votes", {}).get("upvotes", [])),
                "downvotes": set(proposal_data.get("votes", {}).get("downvotes", [])),
            }
        else:
            self.votes: Votes = {"upvotes": set(), "downvotes": set()}

    async def _update_redis_votes(self, bot: Qadir):
        """Update Redis with current vote data."""

        if not self.thread_id:
            return

        proposal_data_raw = await bot.redis.get(f"qadir:proposal:{self.thread_id}")

        if proposal_data_raw:
            proposal_data = json.loads(proposal_data_raw)

            # Update the votes in the proposal data
            proposal_data["votes"] = {"upvotes": list(self.votes["upvotes"]), "downvotes": list(self.votes["downvotes"])}

            # Save updated proposal data back to Redis
            await bot.redis.set(f"qadir:proposal:{self.thread_id}", json.dumps(proposal_data))

    async def update_embed(self, message: discord.Message):
        """Update the embed in the message to reflect current vote counts."""

        embeds = message.embeds
        if not embeds or len(embeds) < 2:
            return

        embeds[1].set_field_at(0, name="👍 Upvotes", value=f"`{len(self.votes["upvotes"])}`", inline=True)
        embeds[1].set_field_at(1, name="👎 Downvotes", value=f"`{len(self.votes["downvotes"])}`", inline=True)

        await message.edit(embeds=embeds)

    @discord.ui.button(label="👍", style=discord.ButtonStyle.green, custom_id="upvote")
    async def upvote(self, _: discord.ui.Button, interaction: discord.Interaction):
        """Handle upvote button press."""

        if not self.votes:
            await self._fetch_votes(interaction.client)

        user_id = interaction.user.id

        # Remove from downvotes if present
        if user_id in self.votes["downvotes"]:
            self.votes["downvotes"].remove(user_id)

        # Toggle upvote
        if user_id in self.votes["upvotes"]:
            self.votes["upvotes"].remove(user_id)
            action = "removed your upvote for this proposal. 🚫"
        else:
            self.votes["upvotes"].add(user_id)
            action = "upvoted this proposal. 👍"

        # Update Redis with new vote data
        await self._update_redis_votes(interaction.client)

        # Update the embed in the message
        if interaction.message:
            await self.update_embed(interaction.message)

        await interaction.response.send_message(embed=SuccessEmbed(description=f"You {action}"), ephemeral=True)

    @discord.ui.button(label="👎", style=discord.ButtonStyle.red, custom_id="downvote")
    async def downvote(self, _: discord.ui.Button, interaction: discord.Interaction):
        """Handle downvote button press."""

        if not self.votes:
            await self._fetch_votes(interaction.client)

        user_id = interaction.user.id

        # Remove from upvotes if present
        if user_id in self.votes["upvotes"]:
            self.votes["upvotes"].remove(user_id)

        # Toggle downvote
        if user_id in self.votes["downvotes"]:
            self.votes["downvotes"].remove(user_id)
            action = "removed your downvote for this proposal. 🚫"
        else:
            self.votes["downvotes"].add(user_id)
            action = "downvoted this proposal. 👎"

        # Update Redis with new vote data
        await self._update_redis_votes(interaction.client)

        # Update the embed in the message
        if interaction.message:
            await self.update_embed(interaction.message)

        await interaction.response.send_message(embed=SuccessEmbed(description=f"You {action}"), ephemeral=True)
