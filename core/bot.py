import discord


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

    async def on_ready(self):
        version = self.config.get("app").get("version")

        print("⚙️ \u200b Loaded Cogs:")
        for cogs in self.cogs:
            print(f"  - {cogs}")

        print(f"✅ Logged in as: {self.user} (ID: {self.user.id}) (v{version}) ({len(self.guilds)} guilds)")

    async def on_error(self, event_method, *args, **kwargs):
        return await super().on_error(event_method, *args, **kwargs)
