import asyncio
import logging
from typing import TYPE_CHECKING

import discord

from config import config
from models.proposals import Proposal

from ..embeds import ErrorEmbed, SuccessEmbed
from ..enums import ProposalStatus
from ..views import VotingView

if TYPE_CHECKING:
    from cogs.proposals import ProposalsCog

CHANNEL_ID: int = config["proposals"]["channels"][0]

logger = logging.getLogger("qadir")


class CreateProposalModal(discord.ui.Modal):
    """Modal for creating a proposal."""

    def __init__(self, cog: "ProposalsCog", *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.cog = cog

        self.add_item(discord.ui.InputText(label="Title", max_length=64, style=discord.InputTextStyle.short, required=True))
        self.add_item(discord.ui.InputText(label="Summary", max_length=2048, style=discord.InputTextStyle.long, required=True))
        self.add_item(discord.ui.InputText(label="Reasoning", max_length=2048, style=discord.InputTextStyle.long, required=True))
        self.add_item(discord.ui.InputText(label="Expected Outcome", max_length=2048, style=discord.InputTextStyle.long, required=True))
        self.add_item(discord.ui.TextDisplay(content="Additional information may be added in the proposal thread."))

    # NOTE: The parameters for on_error are incorrectly ordered in the pycord docs
    async def on_error(self, error: Exception, interaction: discord.Interaction) -> None:
        logger.error("[MODAL] CreateProposalModal Error", exc_info=error)
        await interaction.followup.send(embed=ErrorEmbed(), ephemeral=True)

    async def callback(self, interaction: discord.Interaction):
        """Handle the modal submission and create a proposal thread."""

        await interaction.response.defer(ephemeral=True)

        channel: discord.TextChannel = await interaction.client.fetch_channel(CHANNEL_ID)
        count = await Proposal.count()
        title = f"Proposal #{count + 1} - {self.children[0].value}"
        thread = await channel.create_thread(name=title, type=discord.ChannelType.public_thread)

        summary_embed = discord.Embed(title=title, description=self.children[1].value)
        reasoning_embed = discord.Embed(title="Reasoning", description=self.children[2].value)
        outcome_embed = discord.Embed(title="Expected Outcome", description=self.children[3].value)
        outcome_embed.set_footer(text=interaction.user, icon_url=interaction.user.display_avatar.url)

        poll_embed = discord.Embed(description="Please use the buttons below to cast your vote.")
        poll_embed.add_field(name="👍 Upvotes", value="`0`", inline=True)
        poll_embed.add_field(name="👎 Downvotes", value="`0`", inline=True)
        poll_embed.set_footer(text="Voting will close in 24 hours.")

        result = await asyncio.gather(
            thread.send(embed=summary_embed),
            thread.send(embed=reasoning_embed),
            thread.send(embed=outcome_embed),
            thread.send(embed=poll_embed, view=VotingView(self.cog, thread_id=thread.id)),
        )

        await Proposal(
            thread_id=str(thread.id),
            message_id=str(result[-1].id),
            creator_id=str(interaction.user.id),
            created_at=discord.utils.utcnow(),
            status=ProposalStatus.ACTIVE,
        ).insert()

        embed = SuccessEmbed(title="Proposal Created", description=f"Your proposal has been created in {thread.mention}.")
        await interaction.followup.send(embed=embed, ephemeral=True)

        logger.info(f"✅ [PROPOSALS] Proposal Created: {thread.id} ({title})")
