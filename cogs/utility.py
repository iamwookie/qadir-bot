import discord

from discord.ext import commands
from core import QadirBot


class UtilityCog(commands.Cog):
    """A cog for utility commands."""

    def __init__(self, bot: QadirBot):
        self.bot = bot

    @commands.slash_command()
    async def ping(self, ctx: discord.ApplicationContext):
        """Ping the application."""

        await ctx.respond("🟢 Pong!", ephemeral=True)

    @commands.slash_command()
    async def info(self, ctx: discord.ApplicationContext):
        """Information about the application."""

        dev_id = 244662779745665026

        embed = discord.Embed(title="App Information", description=f"A magical application created by <@{dev_id}>.", colour=0x00FF00)
        embed.add_field(name="Version", value=f"`{self.bot.config["app"]["version"]}`")
        embed.add_field(name="Latency", value=f"`{round(self.bot.latency * 100)} ms`")
        embed.add_field(name="Guilds", value=f"`{len(self.bot.guilds)}`", inline=False)

        await ctx.respond(embed=embed, ephemeral=True)

    @commands.slash_command()
    async def help(self, ctx: discord.ApplicationContext):
        """Stop it, get some help."""

        embed = discord.Embed(title="Help", description="List of available commands:", colour=0xFFFFFF)

        for command in self.bot.application_commands:
            if isinstance(command, discord.SlashCommand):
                if not command.guild_ids or (ctx.guild and ctx.guild.id in command.guild_ids):
                    embed.add_field(name=f"/{command.name}", value=command.description or "No description provided.", inline=False)

        await ctx.respond(embed=embed, ephemeral=True)


def setup(bot: QadirBot):
    bot.add_cog(UtilityCog(bot))
