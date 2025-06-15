import tomllib
import discord

with open("config.toml", "rb") as f:
    config = tomllib.load(f)

CHANNEL: int = config.get("proposals").get("threads")[0]

class CreateProposalModal(discord.ui.Modal):
    """Modal for creating a proposal."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.add_item(discord.ui.InputText(label="Title", style=discord.InputTextStyle.short, required=True))
        self.add_item(discord.ui.InputText(label="Summary", style=discord.InputTextStyle.long, required=True))
        self.add_item(discord.ui.InputText(label="Reasoning", style=discord.InputTextStyle.long, required=True))
        self.add_item(discord.ui.InputText(label="Expected Outcome", style=discord.InputTextStyle.long, required=True))

    async def callback(self, interaction: discord.Interaction):
        target = await interaction.guild.fetch_channel(CHANNEL)

        await interaction.response.send_message("Success!")
