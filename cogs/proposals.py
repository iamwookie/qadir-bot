import logging

import discord
from discord.ext import tasks

from config import config
from core import Cog, Qadir
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

        # MongoDB collection wrapper
        self.db = bot.db["proposals"]

        # Start cog tasks
        self.restore_voting_views.start()
        self.process_proposals.start()

    def cog_unload(self):
        """Clean up tasks when cog is unloaded."""

        self.restore_voting_views.cancel()
        self.process_proposals.cancel()

    async def cog_check(self, ctx: discord.ApplicationContext) -> bool:
        """
        Restrict commands to users with allowed roles.

        Args:
            ctx (discord.ApplicationContext): The application context
        Returns:
            bool: True if user has an allowed role, False otherwise
        """

        return any(role.id in ROLE_IDS for role in ctx.author.roles)

    async def save_proposal_to_db(self, proposal_data: dict) -> bool:
        """
        Save a proposal to MongoDB.

        Args:
            proposal_data: Dictionary containing proposal information

        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            await self.db.insert_one(proposal_data)
            logger.debug(f"[PROPOSALS] Saved proposal {proposal_data.get('thread_id')} to MongoDB")
            return True
        except Exception as e:
            logger.error(f"[PROPOSALS] Error saving proposal to MongoDB: {e}")
            return False

    @tasks.loop(count=1)
    async def restore_voting_views(self) -> None:
        """Restore voting views from MongoDB on bot startup."""

        logger.debug("⌛ [PROPOSALS] Restoring Voting Views...")

        # Get all active proposals from MongoDB
        proposals = await self.db.find({"status": ProposalStatus.ACTIVE.value}).to_list()

        if not proposals:
            logger.debug("⌛ [PROPOSALS] No Voting Views To Restore")
            return

        restored = 0

        for proposal_data in proposals:
            try:
                # Try to fetch the thread and message
                thread: discord.Thread = await self.bot.fetch_channel(proposal_data["thread_id"])
                if not thread:
                    continue

                message: discord.Message = await thread.fetch_message(proposal_data["message_id"])
                if not message:
                    continue

                # Create and add the view to the message
                view = VotingView(self, thread.id)
                self.bot.add_view(view, message_id=message.id)

                restored += 1
            except (discord.NotFound, discord.Forbidden):
                # Thread or message no longer exists, clean up MongoDB
                await self.db.delete_one({"thread_id": proposal_data["thread_id"]})
                logger.warning(f"[PROPOSALS] Cleaned Up Non-Existent Proposal: {proposal_data['thread_id']}")
            except Exception:
                logger.exception(f"[PROPOSALS] Error Restoring View For Proposal: {proposal_data['thread_id']}")

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

        proposals = await self.db.find({"status": ProposalStatus.ACTIVE.value}).to_list()

        if not proposals:
            logger.debug("⌛ [PROPOSALS] No Proposals To Process")
            return

        processed = 0

        for proposal_data in proposals:
            try:
                thread: discord.Thread = await self.bot.fetch_channel(proposal_data["thread_id"])
                message: discord.Message = await thread.fetch_message(proposal_data["message_id"])

                if (discord.utils.utcnow() - message.created_at).total_seconds() < 86400:
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

                await self.db.update_one({"thread_id": proposal_data["thread_id"]}, {"$set": {"status": ProposalStatus.CLOSED.value}})

                processed += 1
            except (discord.NotFound, discord.Forbidden):
                # Thread or message no longer exists, clean up MongoDB
                await self.db.delete_one({"thread_id": proposal_data["thread_id"]})
                logger.warning(f"[TASK] Cleaned Up Non-Existent Proposal: {proposal_data['thread_id']}")
            except Exception:
                logger.exception(f"[TASK] Error Processing Proposal: {proposal_data['thread_id']}")

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

        modal = CreateProposalModal(self, title="Create a Proposal")

        await ctx.send_modal(modal)


def setup(bot: Qadir) -> None:
    """
    Load the ProposalsCog into the bot.

    Args:
        bot (Qadir): The bot instance to load the cog into.
    """

    bot.add_cog(ProposalsCog(bot))
