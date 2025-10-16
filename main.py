import logging
import sys

from discord import Intents

from config import DISCORD_TOKEN, PYTHON_ENV, config
from core import Qadir

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG if config["app"]["debug"] else None)

    logger = logging.getLogger("qadir")
    logger.propagate = False
    logger.setLevel(logging.INFO if PYTHON_ENV == "production" else logging.DEBUG)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")

    file_handler = logging.FileHandler(filename="qadir.log", encoding="utf-8", mode="w")
    file_handler.formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)

    # Enable default intents and add privileged intents
    intents = Intents.default()
    intents.members = True  # Privileged intent
    intents.presences = True  # Privileged intent

    bot = Qadir(intents=intents)

    bot.load_extension("cogs.utility")
    # bot.load_extension("cogs.activities")
    bot.load_extension("cogs.proposals")
    bot.load_extension("cogs.events")
    bot.load_extension("cogs.hangar")

    bot.run(DISCORD_TOKEN)
