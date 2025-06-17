import tomllib
import discord

from discord.ext import commands
from core import QadirBot
from modals import CreateProposalModal

with open("config.toml", "rb") as f:
    config = tomllib.load(f)

GUILD_IDS: list[int] = config["proposals"]["guilds"]


# guild_ids is a part of command_attrs in CogMeta
class ProposalsCog(commands.Cog, guild_ids=GUILD_IDS):
    """A cog for managing proposals."""

    def __init__(self, bot: QadirBot):
        self.bot = bot

    @commands.slash_command()
    async def propose(self, ctx: discord.ApplicationContext) -> None:
        """Submit a proposal."""

        modal = CreateProposalModal(title="Create a Proposal")
        await ctx.send_modal(modal)


def setup(bot: QadirBot):
    bot.add_cog(ProposalsCog(bot))
