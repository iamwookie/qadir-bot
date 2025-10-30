import os
from typing import TypedDict

import tomllib
from dotenv import load_dotenv

load_dotenv(override=False)

APP_DEBUG = os.getenv("APP_DEBUG", "true").lower() == "true"
PYTHON_ENV = os.getenv("PYTHON_ENV", "development")
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
UPSTASH_REDIS_REST_URL = os.environ["UPSTASH_REDIS_REST_URL"]
UPSTASH_REDIS_REST_TOKEN = os.environ["UPSTASH_REDIS_REST_TOKEN"]
MONGODB_URI = os.environ["MONGODB_URI"]


class AppConfig(TypedDict):
    name: str
    version: str


class ProposalsConfig(TypedDict):
    guilds: list[int]
    channels: list[int]
    roles: list[int]


class EventsConfig(TypedDict):
    guilds: list[int]


class HangarConfig(TypedDict):
    guilds: list[int]


class VoiceConfig(TypedDict):
    channels: list[int]


class Config(TypedDict):
    app: AppConfig
    proposals: ProposalsConfig
    events: EventsConfig
    hangar: HangarConfig
    voice: VoiceConfig


def load_config() -> Config:
    """Load the configuration from the appropriate TOML file based on the environment."""

    path = "config.toml" if PYTHON_ENV == "production" else "config.dev.toml"
    with open(path, "rb") as f:
        return tomllib.load(f)


config: Config = load_config()
