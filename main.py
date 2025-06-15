import logging
import tomllib
import os

from dotenv import load_dotenv
from discord import Intents

# Core
from core import QadirBot

if __name__ == "__main__":
    load_dotenv()

    with open("config.toml", "rb") as f:
        config = tomllib.load(f)

    if config["app"]["debug"]:
        logging.basicConfig(level=logging.DEBUG)

    bot = QadirBot(intents=Intents.default(), config=config)

    bot.load_extension("cogs.utility")
    bot.load_extension("cogs.proposals")

    bot.run(os.getenv("DISCORD_TOKEN"))
