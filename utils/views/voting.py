import logging
from typing import TYPE_CHECKING, TypedDict

import discord

from models.proposals import Proposal
from utils.embeds import ErrorEmbed, SuccessEmbed

if TYPE_CHECKING:
    pass

logger = logging.getLogger("qadir")


class Votes(TypedDict):
    upvotes: set[int]
    downvotes: set[int]


class VotingView(discord.ui.View):
    """
    A view for voting that uses buttons instead of reactions.
    """

    def __init__(self, thread_id: int) -> None:
        super().__init__(timeout=None)

        self.thread_id: int = thread_id
        self.proposal: Proposal | None = None

    async def on_error(self, error, _: discord.ui.Item, interaction: discord.Interaction) -> None:
        logger.error("[VOTING] VotingView Error", exc_info=error)
        await interaction.response.send_message(embed=ErrorEmbed(), ephemeral=True)

    async def update_embed(self, message: discord.Message):
        """Update the embed in the message to reflect current vote counts."""

        embeds = message.embeds
        embeds[0].set_field_at(0, name="👍 Upvotes", value=f"`{len(self.proposal.votes.upvotes)}`", inline=True)
        embeds[0].set_field_at(1, name="👎 Downvotes", value=f"`{len(self.proposal.votes.downvotes)}`", inline=True)
        await message.edit(embeds=embeds)

    @discord.ui.button(label="👍", style=discord.ButtonStyle.green, custom_id="upvote")
    async def upvote(self, _: discord.ui.Button, interaction: discord.Interaction):
        """Handle upvote button press."""

        if not self.proposal:
            self.proposal = await Proposal.find_one({"thread_id": str(self.thread_id)})

        user_id = interaction.user.id

        # Remove from downvotes if present
        if str(user_id) in self.proposal.votes.downvotes:
            self.proposal.votes.downvotes.remove(str(user_id))

        # Toggle upvote
        if str(user_id) in self.proposal.votes.upvotes:
            self.proposal.votes.upvotes.remove(str(user_id))
            action = "removed your upvote for this proposal 🚫"
        else:
            self.proposal.votes.upvotes.append(str(user_id))
            action = "upvoted this proposal 👍"

        # Update Redis with new vote data
        await self.proposal.replace()

        # Update the embed in the message
        if interaction.message:
            await self.update_embed(interaction.message)

        await interaction.response.send_message(embed=SuccessEmbed(description=f"You {action}"), ephemeral=True)

    @discord.ui.button(label="👎", style=discord.ButtonStyle.red, custom_id="downvote")
    async def downvote(self, _: discord.ui.Button, interaction: discord.Interaction):
        """Handle downvote button press."""

        if not self.proposal:
            self.proposal = await Proposal.find_one({"thread_id": str(self.thread_id)})

        user_id = interaction.user.id

        # Remove from upvotes if present
        if str(user_id) in self.proposal.votes.upvotes:
            self.proposal.votes.upvotes.remove(str(user_id))

        # Toggle downvote
        if str(user_id) in self.proposal.votes.downvotes:
            self.proposal.votes.downvotes.remove(str(user_id))
            action = "removed your downvote for this proposal 🚫"
        else:
            self.proposal.votes.downvotes.append(str(user_id))
            action = "downvoted this proposal 👎"

        # Update Redis with new vote data
        await self.proposal.replace()

        # Update the embed in the message
        if interaction.message:
            await self.update_embed(interaction.message)

        await interaction.response.send_message(embed=SuccessEmbed(description=f"You {action}"), ephemeral=True)
