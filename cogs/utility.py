from discord.ext import commands
from discord import SlashCommandGroup, Embed
from core import QadirBot


class UtilityCog(commands.Cog):
    """A cog for utility commands."""

    def __init__(self, bot: QadirBot):
        self.bot = bot

    @commands.slash_command()
    async def ping(self, ctx):
        """Responds with latency information."""

        ping = round(self.bot.latency * 1000)  # Convert to milliseconds
        embed = Embed(
            title="Pong!", description=f"Latency: `{ping} ms`", color=0x00FF00
        )

        await ctx.respond(embed=embed)

    @commands.slash_command()
    async def info(self, ctx):
        """Displays information about the app."""

        embed = Embed(
            title="App Information",
            description="This is a magical app created by <@244662779745665026>.",
            color=0x00FF00,
        )
        embed.add_field(name="Bot User", value=f"`{self.bot.user}`", inline=True)
        embed.add_field(name="Bot ID", value=f"`{self.bot.user.id}`", inline=True)

        await ctx.respond(embed=embed)


def setup(bot: QadirBot):
    bot.add_cog(UtilityCog(bot))
    print("⚙️ \u200b Utility cog loaded.")
