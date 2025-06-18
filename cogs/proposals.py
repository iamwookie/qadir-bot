import tomllib
import logging
import discord

from discord.ext import commands
from core import QadirBot
from modals import CreateProposalModal

with open("config.toml", "rb") as f:
    config = tomllib.load(f)

GUILD_IDS: list[int] = config["proposals"]["guilds"]
ROLE_IDS: list[int] = config["proposals"]["roles"]

logger = logging.getLogger("qadir")


# guild_ids is a part of command_attrs in CogMeta
class ProposalsCog(commands.Cog, guild_ids=GUILD_IDS):
    """A cog for managing proposals."""

    def __init__(self, bot: QadirBot):
        self.bot = bot

    async def cog_check(self, ctx: discord.ApplicationContext) -> bool:
        """Check if the command is used by allowed roles."""

        for role_id in ROLE_IDS:
            if role_id in [role.id for role in ctx.author.roles]:
                return True

        return ctx.guild is not None and ctx.guild.id in GUILD_IDS

    @commands.slash_command()
    @commands.has_any_role(*ROLE_IDS)
    async def propose(self, ctx: discord.ApplicationContext) -> None:
        """Submit a proposal."""

        modal = CreateProposalModal(title="Create a Proposal")
        await ctx.send_modal(modal)

    async def cog_command_error(self, ctx: discord.ApplicationContext, error: Exception) -> None:
        """Handle command errors."""

        try:
            if isinstance(error, (commands.MissingRole, commands.MissingAnyRole)):
                await ctx.respond("You do not have permission to use this command.", ephemeral=True)
            else:
                logger.error("[COG] ProposalsCog Error:", exc_info=error)
        except Exception:
            logger.exception("[COG] ProposalsCog Handler Error:")


def setup(bot: QadirBot):
    bot.add_cog(ProposalsCog(bot))
