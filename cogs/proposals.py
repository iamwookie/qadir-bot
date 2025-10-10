import json
import logging
from datetime import datetime, timezone

import discord
from discord.ext import tasks

from config import config
from core import Cog, Qadir
from modals import CreateProposalModal

# TODO: Seperate ProposalStatus and other types into their own file
from modals.create_proposal import ProposalStatus
from views import VotingView

GUILD_IDS: list[int] = config["proposals"]["guilds"]
ROLE_IDS: list[int] = config["proposals"]["roles"]

logger = logging.getLogger("qadir")


class ProposalsCog(Cog, name="Proposals", guild_ids=GUILD_IDS):
    """
    A cog to manage proposals and voting using 👍/👎 reactions.
    Ensures users can only vote one way per proposal, and processes results after 24 hours.
    """

    def __init__(self, bot: Qadir) -> None:
        """
        Initialize the cog and start the proposal processing loop.

        Args:
            bot (Qadir): The bot instance to load the cog into
        """

        super().__init__(bot)

        # Start cog tasks
        self.process_proposals.start()
        self.restore_voting_views.start()

    # def cog_unload(self):
    #     """Clean up tasks when cog is unloaded."""

    #     self.process_proposals.cancel()
    #     self.restore_voting_views.cancel()

    async def cog_check(self, ctx: discord.ApplicationContext) -> bool:
        """
        Restrict commands to users with allowed roles.

        Args:
            ctx (discord.ApplicationContext): The application context
        Returns:
            bool: True if user has an allowed role, False otherwise
        """

        return any(role.id in ROLE_IDS for role in ctx.author.roles)

    @tasks.loop(count=1)
    async def restore_voting_views(self) -> None:
        """Restore voting views from Redis on bot startup."""

        logger.debug("⌛ [PROPOSALS] Restoring Voting Views...")

        # Get all proposal thread IDs from Redis
        proposal_ids = await self.bot.redis.smembers("qadir:proposals")

        if not proposal_ids:
            logger.debug("⌛ [PROPOSALS] No Voting Views To Restore")
            return

        restored = 0

        for thread_id_str in proposal_ids:
            try:
                # Get proposal data
                proposal_data_raw = await self.bot.redis.get(f"qadir:proposal:{thread_id_str}")

                if not proposal_data_raw:
                    continue

                proposal_data = json.loads(proposal_data_raw)

                # Try to fetch the thread and message

                thread: discord.Thread = await self.bot.fetch_channel(int(proposal_data["thread_id"]))
                if not thread:
                    continue

                message: discord.Message = await thread.fetch_message(int(proposal_data["message_id"]))
                if not message:
                    continue

                # Create and add the view to the message
                view = VotingView(thread.id)
                self.bot.add_view(view, message_id=message.id)

                restored += 1
            except (discord.NotFound, discord.Forbidden):
                # Thread or message no longer exists, clean up Redis
                await self.bot.redis.delete(f"qadir:proposal:{thread_id_str}")
                await self.bot.redis.srem("qadir:proposals", thread_id_str)
                logger.warning(f"[PROPOSALS] Cleaned Up Non-Existent Proposal: {thread_id_str}")
            except Exception:
                logger.exception(f"[PROPOSALS] Error Restoring View For Proposal: {thread_id_str}")

        logger.debug(f"⌛ [PROPOSALS] Restored {restored} Voting Views")

    @restore_voting_views.before_loop
    async def before_restore_voting_views(self) -> None:
        """Wait until the bot is ready before restoring voting views."""

        await self.bot.wait_until_ready()

    @restore_voting_views.error
    async def restore_voting_views_error(self, error: Exception) -> None:
        """
        Handle errors in the restore_voting_views loop.

        Args:
            error (Exception): The raised exception
        """

        logger.error("⌛ [PROPOSALS] Error Restoring Voting Views", exc_info=error)

    @tasks.loop(hours=24)
    async def process_proposals(self) -> None:
        """
        Process and finalize proposals that are over a day old.

        Posts results and locks threads.
        """

        logger.debug("⌛ [PROPOSALS] Processing Proposals...")

        proposals = await self.bot.redis.smembers("qadir:proposals")

        if not proposals:
            logger.debug("⌛ [PROPOSALS] No Proposals To Process")
            return

        processed = 0

        for thread_id_str in proposals:
            try:

                proposal_data_raw = await self.bot.redis.get(f"qadir:proposal:{thread_id_str}")

                if not proposal_data_raw:
                    continue

                proposal_data = json.loads(proposal_data_raw)

                thread: discord.Thread = await self.bot.fetch_channel(proposal_data["thread_id"])
                message: discord.Message = await thread.fetch_message(proposal_data["message_id"])

                if (datetime.now(timezone.utc) - message.created_at).total_seconds() < 86400:
                    continue

                upvotes: int = len(proposal_data["votes"]["upvotes"])
                downvotes: int = len(proposal_data["votes"]["downvotes"])

                embed = discord.Embed(title="Proposal Closed", description="Voting has ended for this proposal.", colour=0xFF0000)
                embed.add_field(name="👍 Upvotes", value=f"`{upvotes}`", inline=True)
                embed.add_field(name="👎 Downvotes", value=f"`{downvotes}`", inline=True)

                await message.edit(view=None)
                await thread.send(embed=embed)
                await thread.edit(locked=True)

                proposal_data["status"] = ProposalStatus.CLOSED.value

                await self.bot.redis.srem("qadir:proposals", thread_id_str)
                await self.bot.redis.set(f"qadir:proposal:{thread_id_str}", json.dumps(proposal_data))

                processed += 1
            except (discord.NotFound, discord.Forbidden):
                # Thread or message no longer exists, clean up Redis
                await self.bot.redis.delete(f"qadir:proposal:{thread_id_str}")
                await self.bot.redis.srem("qadir:proposals", thread_id_str)
                logger.warning(f"[TASK] Cleaned Up Non-Existent Proposal: {thread_id_str}")
            except Exception:
                logger.exception(f"[TASK] Error Processing Proposal: {thread_id_str}")

        logger.debug(f"⌛ [PROPOSALS] Processed {processed} Proposals")

    @process_proposals.before_loop
    async def before_process_proposals(self) -> None:
        """
        Wait until the bot is ready before processing proposals.
        """

        await self.bot.wait_until_ready()

    @process_proposals.error
    async def process_proposals_error(self, error: Exception) -> None:
        """
        Handle errors in the process_proposals loop.

        Args:
            error (Exception): The raised exception
        """

        logger.error("⌛ [PROPOSALS] Error Processing Proposals", exc_info=error)

    @discord.slash_command(description="Submit a proposal")
    async def propose(self, ctx: discord.ApplicationContext) -> None:
        """
        Send a CreateProposalModal to submit a proposal.

        Args:
            ctx (discord.ApplicationContext): The application context
        """

        modal = CreateProposalModal(title="Create a Proposal")

        await ctx.send_modal(modal)


def setup(bot: Qadir) -> None:
    """
    Load the ProposalsCog into the bot.

    Args:
        bot (Qadir): The bot instance to load the cog into.
    """

    bot.add_cog(ProposalsCog(bot))
