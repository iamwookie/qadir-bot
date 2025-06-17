import logging
import discord

logger = logging.getLogger("qadir")


class QadirBot(discord.Bot):
    """A custom Discord bot class for Qadir."""

    def __init__(self, *args, **options):
        self.__config = options.pop("config", None)

        if self.__config:
            print("✅ Configuration loaded successfully.")
        else:
            raise ValueError("Configuration is empty!")

        print("⏳ Initializing...")

        super().__init__(*args, **options)

    @property
    def config(self) -> dict:
        """Configuration settings for the Bot."""
        return self.__config

    async def on_ready(self) -> None:
        version = self.config.get("app").get("version")

        print("⚙️ \u200b Loaded Cogs:")
        for cogs in self.cogs:
            print(f"  - {cogs}")

        print(f"✅ Logged in as: {self.user} (v{version}) ({round(self.latency * 1000)}ms) ({len(self.guilds)} guilds)")

    async def on_application_command_error(self, _: discord.ApplicationContext, exception: Exception):
        logger.error("Application Command Error:", exc_info=exception)
