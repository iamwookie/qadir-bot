import logging

from discord import ApplicationContext, Bot
from upstash_redis.asyncio import Redis

from config import config

logger = logging.getLogger("qadir")


class QadirBot(Bot):
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

    async def on_application_command_error(self, _: ApplicationContext, exception: Exception) -> None:
        logger.error("[BOT] Application command error:", exc_info=exception)
