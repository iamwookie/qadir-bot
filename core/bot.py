import asyncio
import logging

import discord
from beanie import init_beanie
from discord.errors import CheckFailure
from discord.ext.commands import CommandOnCooldown
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from upstash_redis.asyncio import Redis

from config import MONGODB_URI, PYTHON_ENV, config
from utils.embeds import ErrorEmbed

logger = logging.getLogger("qadir")


class Qadir(discord.Bot):
    """A custom Discord bot class for Qadir."""

    def __init__(self, *args, **options):
        name = config["app"]["name"]
        version = config["app"]["version"]

        logger.info(f"⏳ {name} (v{version}) Initializing...")

        # Event to track if the bot is fully initialised
        self._initialised: asyncio.Event = asyncio.Event()

        # Redis - Caching and Session Store
        self.redis: Redis = Redis.from_env()

        # MongoDB - Database
        self.mongo: AsyncMongoClient = AsyncMongoClient(MONGODB_URI)
        self.db: AsyncDatabase = self.mongo["qadir-main" if PYTHON_ENV == "production" else "qadir-dev"]

        super().__init__(*args, **options)

    async def on_ready(self) -> None:
        """Called when the bot is ready."""

        await init_beanie(
            database=self.db,
            document_models=[
                "models.proposals.Proposal",
                "models.events.Event",
                "models.hangar.HangarEmbedItem",
            ],
        )

        for cog in self.cogs:
            logger.info(f"🔗 Loaded Cog: {cog}")

        await self.change_presence(activity=discord.CustomActivity(name=f"🌐 v{config['app']['version']} • /help"))

        if not self._initialised.is_set():
            self._initialised.set()

        logger.info(f"✅ Initialised: {self.user} ({round(self.latency * 1000)}ms) ({len(self.guilds)} guilds)")

    async def get_or_fetch_message(self, message_id: int, channel_id: int) -> discord.Message | None:
        """
        Get a message from the cache or fetch it from the API.

        Args:
            message_id (int): The ID of the message to get
            channel_id (int): The ID of the channel containing the message
        """

        try:
            message = self.get_message(message_id)
            if not message:
                channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
                message = await channel.fetch_message(message_id)
            return message
        except Exception:
            logger.exception(f"[QADIR] Error Getting/Fetching Message: {message_id} <- {channel_id}")
            return None

    async def on_application_command_error(self, ctx: discord.ApplicationContext, exception: Exception) -> None:
        """
        Handle errors for application commands for the entire application.

        Args:
            ctx (discord.ApplicationContext): The application context
            exception (Exception): The exception that was raised
        """

        try:
            if isinstance(exception, CheckFailure):
                embed = ErrorEmbed("Permission Denied", "You do not have permission to use this command")
                await ctx.respond(embed=embed, ephemeral=True)
            elif isinstance(exception, CommandOnCooldown):
                embed = ErrorEmbed(
                    "Command On Cooldown",
                    f"This command is on cooldown, try again in `{exception.retry_after:.2f}` seconds",
                )
                await ctx.respond(embed=embed, ephemeral=True)
            else:
                logger.error("[COG] Application Command Error", exc_info=exception)
        except Exception:
            logger.exception("[QADIR] Application Command Handler Error")

    async def wait_until_initialised(self) -> None:
        """Wait until the bot is fully initialised."""

        await self._initialised.wait()
