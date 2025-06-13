import discord


class QadirBot(discord.Bot):
    def __init__(self, description=None, *args, **options):
        super().__init__(description, *args, **options)

    async def on_ready(self):
        print(f"Logged in as {self.user}")
