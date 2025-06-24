from dotenv import load_dotenv

import sys
import tomllib
import logging
import os

# Discord
from discord import Intents

# Core
from core import QadirBot

if __name__ == "__main__":
    if os.getenv("PYTHON_ENV") == "production":
        with open("config.toml", "rb") as f:
            config = tomllib.load(f)
    else:
        load_dotenv(override=True)

        with open("config.dev.toml", "rb") as f:
            config = tomllib.load(f)

    logging.basicConfig(level=logging.DEBUG if config["app"]["debug"] else None)

    logger = logging.getLogger("qadir")
    logger.propagate = False
    logger.setLevel(logging.DEBUG if config["app"]["debug"] else logging.INFO)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")

    file_handler = logging.FileHandler(filename="qadir.log", encoding="utf-8", mode="w")
    file_handler.formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)

    bot = QadirBot(intents=Intents.default(), config=config)

    bot.load_extension("cogs.utility")
    bot.load_extension("cogs.proposals")

    bot.run(os.getenv("DISCORD_TOKEN"))
