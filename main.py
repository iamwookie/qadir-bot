import logging
import sys

from discord import Intents

from config import APP_DEBUG, DISCORD_TOKEN
from core import Qadir

if __name__ == "__main__":
    logger = logging.getLogger("qadir")
    logger.propagate = False
    logger.setLevel(logging.DEBUG if APP_DEBUG else logging.INFO)

    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.formatter = formatter

    file_handler = logging.FileHandler(filename="qadir.log", encoding="utf-8", mode="w")
    file_handler.formatter = formatter
    file_handler.setLevel(logging.DEBUG)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)
    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)

    # Enable default intents and add privileged intents
    intents = Intents.default()
    intents.members = True  # Privileged intent
    intents.presences = True  # Privileged intent

    bot = Qadir(intents=intents)

    bot.load_extension("cogs.utility")
    bot.load_extension("cogs.proposals")
    bot.load_extension("cogs.events")
    bot.load_extension("cogs.hangar")
    bot.load_extension("cogs.voice")

    bot.run(DISCORD_TOKEN)
