import os

from dotenv import load_dotenv
from discord import Intents
from bot import QadirBot

load_dotenv()

bot = QadirBot(intents=Intents.default())

bot.run(os.getenv("DISCORD_TOKEN"))
