import json
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from config import config
from core import Cog, Qadir
from modals import CreateProposalModal

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

        :param bot: The Qadir instance
        """

        super().__init__(bot)

        self.process_proposals.start()

    async def cog_check(self, ctx: discord.ApplicationContext) -> bool:
        """
        Restrict commands to users with allowed roles.

        :param ctx: The application context
        :return: True if user is authorized
        """

        return any(role.id in ROLE_IDS for role in ctx.author.roles)

    @tasks.loop(hours=24)
    async def process_proposals(self) -> None:
        """
        Process and finalize proposals that are over 24 hours old.
        Posts results and locks threads.
        """

        logger.info("⌛ Running proposals processing...")

        proposals = await self.bot.redis.smembers("qadir:proposals")
        proposals = [json.loads(p) for p in proposals]

        if not proposals:
            logger.info("⌛ No proposals to process.")
            return

        for data in proposals:
            try:
                thread: discord.Thread = await self.bot.fetch_channel(data["thread_id"])
                message: discord.Message = await thread.fetch_message(data["message_id"])

                await self.cleanup_conflicting_votes(message)

                if (datetime.now(timezone.utc) - message.created_at).total_seconds() < 86400:
                    continue

                upvotes: int = sum(r.count for r in message.reactions if r.emoji == "👍") - 1
                downvotes: int = sum(r.count for r in message.reactions if r.emoji == "👎") - 1

                embed = discord.Embed(title="Proposal Closed", description="Voting has ended for this proposal.", colour=0xFF0000)
                embed.add_field(name="Upvotes", value=f"`{upvotes}`", inline=True)
                embed.add_field(name="Downvotes", value=f"`{downvotes}`", inline=True)

                await thread.send(embed=embed)
                await thread.edit(locked=True)

                await self.bot.redis.srem("qadir:proposals", json.dumps(data))
            except discord.NotFound:
                logger.warning(f"[TASK] Proposal {data['thread_id']} Not Found")
                await self.bot.redis.srem("qadir:proposals", json.dumps(data))
            except Exception:
                logger.exception(f"[TASK] Error Processing Proposal {data['thread_id']}")

        logger.info(f"⌛ Processed {len(proposals)} proposals.")

    @process_proposals.before_loop
    async def before_process_proposals(self) -> None:
        """
        Wait until the bot is ready before running the proposal loop.
        """

        await self.bot.wait_until_ready()

    @process_proposals.error
    async def process_proposals_error(self, error: Exception) -> None:
        """
        Handle errors in the proposal loop.

        :param error: The raised exception
        """

        logger.error("[TASK] Proposals Processing Error", exc_info=error)

    @discord.slash_command()
    @commands.has_any_role(*ROLE_IDS)
    async def propose(self, ctx: discord.ApplicationContext) -> None:
        """
        Submit a proposal via a modal form.

        :param ctx: The application context
        """

        modal = CreateProposalModal(title="Create a Proposal")

        await ctx.send_modal(modal)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User | discord.Member) -> None:
        """
        Fast, live handler for new reactions on cached messages.

        :param reaction: The added reaction
        :param user: The reacting user
        """
        if user.bot:
            return

        await self.handle_vote_conflict(reaction.message, user, str(reaction.emoji))

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """
        Reliable fallback handler for all reactions, even on uncached messages.

        :param payload: The raw reaction event
        """

        if payload.user_id == self.bot.user.id:
            return

        try:
            channel: discord.abc.Messageable = await self.bot.fetch_channel(payload.channel_id)
            message: discord.Message = await channel.fetch_message(payload.message_id)
            user: discord.User = await self.bot.fetch_user(payload.user_id)

            await self.handle_vote_conflict(message, user, str(payload.emoji))
        except Exception:
            logger.exception("[RAW] Failed To Process Raw Reaction Event")

    async def handle_vote_conflict(self, message: discord.Message, user: discord.User, new_emoji: str) -> None:
        """
        Remove conflicting vote emoji if user has already voted oppositely.

        :param message: The message the user reacted to
        :param user: The user who reacted
        :param new_emoji: The emoji they just added
        """

        vote_emojis: dict[str, str] = {"👍": "👎", "👎": "👍"}
        conflicting_emoji: str | None = vote_emojis.get(new_emoji)

        if conflicting_emoji is None:
            return

        tracked = await self.bot.redis.smembers("qadir:proposals")
        tracked_ids = {int(json.loads(p)["message_id"]) for p in tracked}

        if message.id not in tracked_ids:
            return

        for r in message.reactions:
            if str(r.emoji) == conflicting_emoji:
                users = await r.users().flatten()

                if any(u.id == user.id for u in users):
                    await r.remove(user)
                    logger.info(f"[VOTES] Removed conflicting vote '{conflicting_emoji}' from {user.name} on {message.id}.")

    async def cleanup_conflicting_votes(self, message: discord.Message) -> None:
        """
        Remove older conflicting votes from users who reacted with both 👍 and 👎.

        Keeps only the last emoji in message.reactions order (assumed latest).

        :param message: The message containing the reactions
        """

        try:
            user_votes: dict[int, list[str]] = {}
            emoji_order: list[str] = []

            for reaction in message.reactions:
                if reaction.emoji not in {"👍", "👎"}:
                    continue

                emoji_order.append(reaction.emoji)
                users = await reaction.users().flatten()

                for u in users:
                    if u.bot:
                        continue

                    user_votes.setdefault(u.id, []).append(reaction.emoji)

            for user_id, votes in user_votes.items():
                if len(set(votes)) <= 1:
                    continue

                # Keep the last seen emoji from the defined order
                emojis = set(votes)

                for emoji in reversed(emoji_order):
                    if emoji in emojis:
                        keep_emoji = emoji
                        break

                for reaction in message.reactions:
                    if reaction.emoji in {"👍", "👎"} and reaction.emoji != keep_emoji:
                        users = await reaction.users().flatten()

                        for u in users:
                            if u.id == user_id:
                                await reaction.remove(u)
                                logger.info(f"[CLEANUP] Removed older vote '{reaction.emoji}' from user {u.name} on message {message.id}.")
        except Exception:
            logger.exception("[VOTING] Error Cleaning Up Conflicting Votes")


def setup(bot: Qadir) -> None:
    """
    Load the ProposalsCog into the bot.

    :param bot: The Qadir instance
    """

    bot.add_cog(ProposalsCog(bot))
