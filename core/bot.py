import logging

from discord import ApplicationContext, Bot
from discord.ext import commands
from upstash_redis.asyncio import Redis

from config import config

from .embeds import ErrorEmbed

logger = logging.getLogger("qadir")


class Qadir(Bot):
    """A custom Discord bot class for Qadir."""

    def __init__(self, *args, **options):
        logger.info("⏳ Initializing...")

        # Database
        self.redis = Redis.from_env()

        super().__init__(*args, **options)

    async def on_ready(self) -> None:
        version = config["app"]["version"]

        for cog in self.cogs:
            logger.info(f"🔗 Loaded Cog: {cog}")

        logger.info(f"✅ Logged in: {self.user} (v{version}) ({round(self.latency * 1000)}ms) ({len(self.guilds)} guilds).")

    async def on_application_command_error(self, ctx: ApplicationContext, exception: Exception) -> None:
        """
        Handle errors for application commands for the entire application.

        :param ctx: The application context
        :param exception: The raised exception
        """

        try:
            if isinstance(exception, (commands.MissingRole, commands.MissingAnyRole)):
                embed = ErrorEmbed(description="You do not have permission to use this command")
                await ctx.respond(embed=embed, ephemeral=True)
            elif isinstance(exception, commands.CommandOnCooldown):
                embed = ErrorEmbed(description=f"This command is on cooldown, try again in `{exception.retry_after:.2f}` seconds")
                await ctx.respond(embed=embed, ephemeral=True)
            else:
                logger.error("[COG] Application Command Error", exc_info=exception)
        except Exception:
            logger.exception("[BOT] Application Command Handler Error")
