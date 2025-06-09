import discord

from dotenv import load_dotenv
from client import Client

load_dotenv()

bot = discord.Bot(intents=discord.Intents.default())

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

bot.run(os.getenv("DISCORD_TOKEN"))
