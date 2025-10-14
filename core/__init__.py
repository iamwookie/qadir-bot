from discord.ext import commands

from .bot import Qadir

__all__ = ["Qadir", "Cog"]


class Cog(commands.Cog):
    """
    A base class for all cogs in Qadir.
    """

    def __init__(self, bot: Qadir) -> None:
        self.bot = bot

        # Redis instance wrapper
        self.redis = bot.redis
