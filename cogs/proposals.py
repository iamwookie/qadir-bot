import logging

import discord
from discord.ext import tasks

from config import config
from core import Cog, Qadir
from models.proposals import Proposal
from utils.enums import ProposalStatus
from utils.modals import CreateProposalModal
from utils.views import VotingView

GUILD_IDS = config["proposals"]["guilds"]
ROLE_IDS = config["proposals"]["roles"]

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
        self._process_proposals.start()
        self._restore_voting_views.start()

    def cog_unload(self):
        """Clean up tasks when cog is unloaded."""

        self._process_proposals.cancel()
        self._restore_voting_views.cancel()

    async def cog_check(self, ctx: discord.ApplicationContext) -> bool:
        """
        Restrict commands to users with allowed roles.

        Args:
            ctx (discord.ApplicationContext): The application context
        Returns:
            bool: True if user has an allowed role, False otherwise
        """

        return any(role.id in ROLE_IDS for role in ctx.author.roles)

    @tasks.loop(hours=12)
    async def _process_proposals(self) -> None:
        """Process and finalize proposals that are over a day old."""

        logger.debug("⌛🔄 [PROPOSALS] [0] Processing Proposals...")

        proposals = await Proposal.find(Proposal.status == ProposalStatus.ACTIVE).to_list()

        if not proposals:
            logger.debug("⌛✅️ [PROPOSALS] [0] No Proposals To Process")
            return

        processed = 0

        for proposal in proposals:
            try:
                thread: discord.Thread = await self.bot.get_or_fetch_channel(int(proposal.thread_id))
                message: discord.Message = thread.get_partial_message(int(proposal.message_id))

                if (discord.utils.utcnow() - thread.created_at).total_seconds() < 86400:
                    continue

                upvotes = len(proposal.votes.upvotes)
                downvotes = len(proposal.votes.downvotes)

                embed = discord.Embed(title="Proposal Closed", description="Voting has ended for this proposal", colour=0xFF0000)
                embed.add_field(name="👍 Upvotes", value=f"`{upvotes}`", inline=True)
                embed.add_field(name="👎 Downvotes", value=f"`{downvotes}`", inline=True)

                await message.edit(view=None)
                await thread.send(embed=embed)
                await thread.edit(locked=True)

                proposal.status = ProposalStatus.CLOSED
                await proposal.replace()

                processed += 1
            except (discord.NotFound, discord.Forbidden):
                # Thread or message no longer exists, clean up MongoDB
                await proposal.delete()
                logger.warning(f"⌛⚠️ [PROPOSALS] [0] Cleaned Up Non-Existent Proposal: {proposal.thread_id}")
            except Exception:
                logger.exception(f"⌛❌ [PROPOSALS] [0] Error Processing Proposal: {proposal.thread_id}")

        logger.debug(f"⌛✅️ [PROPOSALS] [0] Processed {processed} Proposals")

    @_process_proposals.before_loop
    async def before_process_proposals(self) -> None:
        """Wait until the bot is initialised before processing proposals."""

        await self.bot.wait_until_initialised()

    @_process_proposals.error
    async def process_proposals_error(self, error: Exception) -> None:
        """
        Handle errors in the process_proposals loop.

        Args:
            error (Exception): The raised exception
        """

        logger.error("⌛❌ [PROPOSALS] Error Processing Proposals", exc_info=error)

    @tasks.loop(count=1)
    async def _restore_voting_views(self) -> None:
        """Restore voting views from MongoDB on bot startup."""

        logger.debug("⌛🔄 [PROPOSALS] [1] Restoring Voting Views...")

        # Get all active proposals from MongoDB
        proposals = await Proposal.find(Proposal.status == ProposalStatus.ACTIVE).to_list()

        if not proposals:
            logger.debug("⌛✅️ [PROPOSALS] [1] No Voting Views To Restore")
            return

        restored = 0

        for proposal in proposals:
            try:
                # Try to fetch the thread and message
                thread = await self.bot.fetch_channel(int(proposal.thread_id))
                if not isinstance(thread, discord.Thread):
                    continue

                message = await thread.fetch_message(int(proposal.message_id))
                if not isinstance(message, discord.Message):
                    continue

                # Create and add the view to the message
                view = VotingView(thread.id)
                self.bot.add_view(view, message_id=message.id)

                restored += 1
            except (discord.NotFound, discord.Forbidden):
                logger.warning(f"⌛⚠️ [PROPOSALS] [1] Proposal Not Found: {proposal.thread_id}")
            except Exception:
                logger.exception(f"⌛❌ [PROPOSALS] [1] Error Restoring View For Proposal: {proposal.thread_id}")

        logger.debug(f"⌛✅️ [PROPOSALS] [1] Restored {restored} Voting Views")

    @_restore_voting_views.before_loop
    async def before_restore_voting_views(self) -> None:
        """Wait until the bot is initialised before restoring voting views."""

        await self.bot.wait_until_initialised()

    @_restore_voting_views.error
    async def restore_voting_views_error(self, error: Exception) -> None:
        """
        Handle errors in the restore_voting_views loop.

        Args:
            error (Exception): The raised exception
        """

        logger.error("⌛❌ [PROPOSALS] [1] Error Restoring Voting Views", exc_info=error)

    @discord.slash_command(description="Submit a proposal")
    async def propose(self, ctx: discord.ApplicationContext) -> None:
        """
        Send a CreateProposalModal to submit a proposal.

        Args:
            ctx (discord.ApplicationContext): The application context
        """

        modal = CreateProposalModal()
        await ctx.send_modal(modal)


def setup(bot: Qadir) -> None:
    """
    Load the ProposalsCog into the bot.

    Args:
        bot (Qadir): The bot instance to load the cog into.
    """

    bot.add_cog(ProposalsCog(bot))
