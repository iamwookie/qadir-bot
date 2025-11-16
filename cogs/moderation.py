import logging

import discord
from discord.ext import commands

from config import config
from core import Cog, Qadir
from utils.embeds import ErrorEmbed, SuccessEmbed

GUILD_IDS = config["moderation"]["guilds"]

logger = logging.getLogger("qadir")


class ModerationCog(Cog, name="Moderation", guild_ids=GUILD_IDS):
    """A cog to manage guild moderation."""

    @discord.slash_command(description="Ban a member from the server")
    @discord.option("member", discord.Member, description="The member to ban")
    @discord.option("reason", str, description="The reason for the ban", required=False, default="N/A")
    @discord.option(
        "delete_message_days",
        int,
        description="Number of days of messages to delete (0-7)",
        required=False,
        default=0,
        min_value=0,
        max_value=7,
    )
    @commands.has_permissions(ban_members=True)
    @commands.cooldown(1, 15.0, commands.BucketType.user)
    async def ban(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Member,
        reason: str,
        delete_message_days: int,
    ) -> None:
        """
        Ban a member from the server.

        Args:
            ctx (discord.ApplicationContext): The application context
            member (discord.Member): The member to ban
            reason (str): The reason for the ban
            delete_message_days (int): Number of days of messages to delete
        """

        # Check if the bot has ban permissions
        if not ctx.guild.me.guild_permissions.ban_members:
            await ctx.respond(
                embed=ErrorEmbed(title="Missing Permissions", description="I do not have permission to ban members"),
                ephemeral=True,
            )
            return

        # Check if trying to ban themselves
        if member.id == ctx.author.id:
            await ctx.respond(
                embed=ErrorEmbed(description="You cannot ban yourself"),
                ephemeral=True,
            )
            return

        # Check if trying to ban myself
        if member.id == ctx.guild.me.id:
            await ctx.respond(
                embed=ErrorEmbed(description="I cannot ban myself"),
                ephemeral=True,
            )
            return

        # Check role hierarchy - user cannot ban someone with equal or higher role
        if ctx.author.top_role <= member.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.respond(
                embed=ErrorEmbed(description=f"You cannot ban {member.mention} because their role is equal to or higher than yours"),
                ephemeral=True,
            )
            return

        # Check role hierarchy - bot cannot ban someone with equal or higher role
        if ctx.guild.me.top_role <= member.top_role:
            await ctx.respond(
                embed=ErrorEmbed(description=f"I cannot ban {member.mention} because their role is equal to or higher than mine"),
                ephemeral=True,
            )
            return

        # Defer the response as banning might take a moment
        await ctx.defer()

        # Perform the ban
        await member.ban(reason=f"{reason} (Banned by {ctx.author.name})", delete_message_seconds=delete_message_days * 86400)

        # Send a beautiful success embed
        embed = SuccessEmbed(title="Member Banned", description=(f"{member.mention} (`{member.id}`) has been banned\n"))
        embed.set_image(url="https://c.tenor.com/9zCgefg___cAAAAd/tenor.gif")
        await ctx.followup.send(embed=embed)

        logger.info(f"[MODERATION] ({ctx.guild.id}) {ctx.author.name} Banned {member.name} ({member.id}) - Reason: {reason}")


def setup(bot: Qadir) -> None:
    """
    Load the ModerationCog into the bot.

    Args:
        bot (Qadir): The bot instance to load the cog into
    """

    bot.add_cog(ModerationCog(bot))
