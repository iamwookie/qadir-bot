import tomllib
import logging
import discord
import datetime
import re

with open("config.toml", "rb") as f:
    config = tomllib.load(f)

CHANNEL_ID: int = config["proposals"]["channels"][0]

logger = logging.getLogger("qadir")


class CreateProposalModal(discord.ui.Modal):
    """Modal for creating a proposal."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.add_item(discord.ui.InputText(label="Title", style=discord.InputTextStyle.short, required=True))
        self.add_item(discord.ui.InputText(label="Summary", style=discord.InputTextStyle.long, required=True))
        self.add_item(discord.ui.InputText(label="Reasoning", style=discord.InputTextStyle.long, required=True))
        self.add_item(discord.ui.InputText(label="Expected Outcome", style=discord.InputTextStyle.long, required=True))

    async def on_error(self, error: Exception) -> None:
        logger.error("[MODAL] CreateProposalModal Error:", exc_info=error)

    def get_last_proposal_number(self, channel: discord.TextChannel) -> int | None:
        """Get the last proposal number from the channel threads."""

        last_thread = channel.threads[-1]
        match = re.search(r"#(\d+)", last_thread.name)
        return int(match.group(1)) if match else None

    async def callback(self, interaction: discord.Interaction):
        """Handle the modal submission and create a proposal thread."""

        await interaction.response.defer(ephemeral=True)

        channel: discord.TextChannel = await interaction.client.fetch_channel(CHANNEL_ID)

        last_number = self.get_last_proposal_number(channel)
        next_number = last_number + 1 if last_number else 1
        thread_title = f"Proposal #{next_number} - {self.children[0].value}"

        thread = await channel.create_thread(name=thread_title, type=discord.ChannelType.public_thread)

        proposal_embed = discord.Embed(title=thread_title, description=self.children[1].value, colour=discord.Colour.blue())
        proposal_embed.add_field(name="Reasoning", value=self.children[2].value, inline=False)
        proposal_embed.add_field(name="Expected Outcome", value=self.children[3].value, inline=False)
        proposal_embed.set_footer(text=interaction.user, icon_url=interaction.user.display_avatar.url)

        poll_embed = discord.Embed(description="Please use the reactions below to cast your vote.")
        poll_embed.set_footer(text="Voting will close in 24 hours.")

        message = await thread.send(embeds=[proposal_embed, poll_embed])

        await message.add_reaction("👍")
        await message.add_reaction("👎")

        await interaction.followup.send(f"Your proposal has been created in {thread.mention}.", ephemeral=True)
