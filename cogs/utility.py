import logging

import discord
from discord.ext import commands

from core import Cog, Qadir
from core.embeds import ErrorEmbed

logger = logging.getLogger("qadir")


class UtilityCog(Cog):
    """A cog for utility commands."""

    @discord.slash_command()
    async def ping(self, ctx: discord.ApplicationContext):
        """Ping the application"""

        await ctx.respond("🟢 Pong!", ephemeral=True)

    @discord.slash_command()
    async def info(self, ctx: discord.ApplicationContext):
        """Information about the application"""

        dev_id = 244662779745665026

        embed = discord.Embed(title="App Information", description=f"A magical application created by <@{dev_id}>", colour=0x00FF00)
        embed.add_field(name="Version", value=f"`{self.bot.config['app']['version']}`")
        embed.add_field(name="Latency", value=f"`{round(self.bot.latency * 100)} ms`")
        embed.add_field(name="Guilds", value=f"`{len(self.bot.guilds)}`", inline=False)

        await ctx.respond(embed=embed, ephemeral=True)

    @discord.slash_command()
    async def help(self, ctx: discord.ApplicationContext):
        """Stop it, get some help"""

        embed = discord.Embed(title="Help", description="Need some help? Gotchu", colour=0xFFFFFF)

        for command in self.bot.application_commands:
            if isinstance(command, discord.SlashCommand):
                if not command.guild_ids or (ctx.guild and ctx.guild.id in command.guild_ids):
                    embed.add_field(name=f"/{command.name}", value=command.description or "No description provided", inline=False)

        await ctx.respond(embed=embed, ephemeral=True)

    @discord.slash_command()
    @discord.option("user_id", str, description="A user to find by ID")
    @commands.cooldown(1, 15.0, commands.BucketType.user)
    async def find(self, ctx: discord.ApplicationContext, user_id: str | None = None):
        """Find information about a user"""

        await ctx.defer(ephemeral=True)

        user_id: str = user_id.strip() if user_id else str(ctx.author.id)

        try:
            user = await self.bot.get_or_fetch_user(int(user_id))
        except discord.NotFound:
            await ctx.respond(embed=ErrorEmbed(title="User not found"), ephemeral=True)
            return
        except ValueError:
            await ctx.respond(embed=ErrorEmbed(title="Invalid user ID provided"), ephemeral=True)
            return

        embed = discord.Embed(title="User Information", colour=0xFFFFFF)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Username", value=f"`{user.name}#{user.discriminator}`")
        embed.add_field(name="User ID", value=f"`{user.id}`")
        embed.add_field(name="Account Created", value=f"<t:{int(user.created_at.timestamp())}:R>", inline=False)

        if isinstance(ctx.guild, discord.Guild):
            try:
                member: discord.Member = ctx.guild.get_member(user.id) or await ctx.guild.fetch_member(user.id)

                if member and member.joined_at:
                    embed.add_field(name="Server Joined", value=f"<t:{int(member.joined_at.timestamp())}:R>", inline=False)

                if member.roles:
                    roles = [role.mention for role in member.roles if role.id != ctx.guild.id]
                    embed.add_field(name="Server Roles", value=" ".join(roles) if roles else "None", inline=False)
            except Exception:
                # Intentionally ignored
                pass

        if user.accent_colour:
            embed.add_field(name="Accent Colour" if user.banner else "Banner Colour", value=f"`{user.accent_colour}`")

        if user.banner:
            embed.set_image(url=user.banner.url)

        if user.bot:
            embed.set_footer(text="⚠️ This user is a bot.")

        await ctx.respond(embed=embed, ephemeral=True)


def setup(bot: Qadir):
    """
    Load the UtilityCog into the bot.

    :param bot: The Qadir instance
    """

    bot.add_cog(UtilityCog(bot))
