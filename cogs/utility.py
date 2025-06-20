from discord import ApplicationContext, Embed
from discord.ext import commands
from core import QadirBot


class UtilityCog(commands.Cog):
    """A cog for utility commands."""

    def __init__(self, bot: QadirBot):
        self.bot = bot

    @commands.slash_command()
    async def ping(self, ctx: ApplicationContext):
        """Ping the application."""

        await ctx.respond("🟢 Pong!", ephemeral=True)

    @commands.slash_command()
    async def info(self, ctx):
        """Displays information about the app."""

        dev_id = 244662779745665026

        embed = Embed(title="App Information", description=f"A magical application created by <@{dev_id}>.", color=0x00FF00)
        embed.add_field(name="Version", value=f"`{self.bot.config["app"]["version"]}`")
        embed.add_field(name="Latency", value=f"`{round(self.bot.latency * 100)} ms`")
        embed.add_field(name="Guilds", value=f"`{len(self.bot.guilds)}`", inline=False)

        await ctx.respond(embed=embed)


def setup(bot: QadirBot):
    bot.add_cog(UtilityCog(bot))
