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
        return self.__config

    async def on_ready(self):
        version = self.config.get("app").get("version", "0")

        print(f"✅ Logged in as: {self.user} (ID: {self.user.id}) (v{version})")
        print(f"🌐 Connected to {len(self.guilds)} guild(s):")

        for guild in self.guilds:
            print(f" - {guild.name} (ID: {guild.id})")
