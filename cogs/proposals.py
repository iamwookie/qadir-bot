import tomllib
import logging
import discord
import json

from discord.ext import commands, tasks
from core import QadirBot
from modals import CreateProposalModal
from datetime import datetime, timezone

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

        # Tasks
        self.process_proposals.start()

    async def cog_check(self, ctx: discord.ApplicationContext) -> bool:
        """Check if the command is used by allowed roles."""

        for role_id in ROLE_IDS:
            if role_id in [role.id for role in ctx.author.roles]:
                return True

        return ctx.guild is not None and ctx.guild.id in GUILD_IDS

    async def cog_command_error(self, ctx: discord.ApplicationContext, error: Exception) -> None:
        """Handle command errors."""

        try:
            if isinstance(error, (commands.MissingRole, commands.MissingAnyRole)):
                await ctx.respond("You do not have permission to use this command.", ephemeral=True)
            else:
                logger.error("[COG] ProposalsCog Error:", exc_info=error)
        except Exception:
            logger.exception("[COG] ProposalsCog Handler Error:")

    @tasks.loop(hours=24)
    async def process_proposals(self) -> None:
        """Process active proposals."""

        logger.info("⌛ Running proposals processing...")

        proposals = await self.bot.redis.smembers("qadir:proposals")
        proposals = [json.loads(data) for data in proposals]

        if not proposals:
            logger.info("⌛ No proposals to process.")
            return

        for data in proposals:
            try:
                thread = await self.bot.fetch_channel(data["thread_id"])
                message = await thread.fetch_message(data["message_id"])

                if (datetime.now(timezone.utc) - message.created_at).total_seconds() < 86400:
                    continue

                upvotes = sum(reaction.count for reaction in message.reactions if reaction.emoji == "👍") - 1
                downvotes = sum(reaction.count for reaction in message.reactions if reaction.emoji == "👎") - 1

                embed = discord.Embed(title="Proposal Closed", description="Voting has ended for this proposal.", colour=0xFF0000)
                embed.add_field(name="Upvotes", value=f"`{str(upvotes)}`", inline=True)
                embed.add_field(name="Downvotes", value=f"`{str(downvotes)}`", inline=True)

                await thread.send(embed=embed)
                await thread.edit(locked=True)

                await self.bot.redis.srem("qadir:proposals", json.dumps(data))
            except discord.NotFound:
                logger.warning(f"[TASK] Proposal {data['thread_id']} Not Found.")
                await self.bot.redis.srem("qadir:proposals", json.dumps(data))
            except Exception:
                logger.exception(f"[TASK] Error Processing Proposal {data['thread_id']}:")

        logger.info(f"⌛ Proccessed {len(proposals)} proposals.")

    @process_proposals.before_loop
    async def before_process_proposals(self) -> None:
        await self.bot.wait_until_ready()

    @process_proposals.error
    async def process_proposals_error(self, error: Exception) -> None:
        logger.error("[TASK] Proposals Processing Error:", exc_info=error)

    @commands.slash_command()
    @commands.has_any_role(*ROLE_IDS)
    async def propose(self, ctx: discord.ApplicationContext) -> None:
        """Submit a proposal."""

        modal = CreateProposalModal(title="Create a Proposal")
        await ctx.send_modal(modal)


def setup(bot: QadirBot):
    bot.add_cog(ProposalsCog(bot))
