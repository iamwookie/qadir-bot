import logging

from discord import ApplicationContext, Bot
from upstash_redis.asyncio import Redis

logger = logging.getLogger("qadir")


class QadirBot(Bot):
    """A custom Discord bot class for Qadir."""

    def __init__(self, *args, **options):
        self.__config = options.pop("config", None)

        logger.info("⏳ Initializing...")

        # Config
        if self.__config:
            logger.info("✅ Configuration loaded successfully.")
        else:
            raise ValueError("Configuration is empty!")

        # Database
        self.redis = Redis.from_env()

        super().__init__(*args, **options)

    @property
    def config(self) -> dict:
        """Configuration settings for the application."""
        return self.__config

    async def on_ready(self) -> None:
        version = self.config.get("app").get("version")

        for cog in self.cogs:
            logger.info(f"🔗 Loaded Cog: {cog}")

        logger.info(f"✅ Logged in: {self.user} (v{version}) ({round(self.latency * 1000)}ms) ({len(self.guilds)} guilds).")

    async def on_application_command_error(self, _: ApplicationContext, exception: Exception) -> None:
        logger.error("[BOT] Application command error:", exc_info=exception)
