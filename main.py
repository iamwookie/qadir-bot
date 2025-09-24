import logging
import os
import sys

from discord import Intents

from config import config
from core import Qadir

if __name__ == "__main__":
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

    bot = Qadir(intents=Intents.default())

    bot.load_extension("cogs.utility")
    bot.load_extension("cogs.proposals")
    bot.load_extension("cogs.loot")

    bot.run(os.getenv("DISCORD_TOKEN"))
