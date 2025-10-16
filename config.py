import os
from typing import TypedDict

import tomllib
from dotenv import load_dotenv

load_dotenv(override=False)

PYTHON_ENV = os.getenv("PYTHON_ENV", "development")
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
UPSTASH_REDIS_REST_URL = os.environ["UPSTASH_REDIS_REST_URL"]
UPSTASH_REDIS_REST_TOKEN = os.environ["UPSTASH_REDIS_REST_TOKEN"]


class AppConfig(TypedDict):
    name: str
    version: str
    debug: bool


class ProposalsConfig(TypedDict):
    guilds: list[int]
    channels: list[int]
    roles: list[int]


class EventsConfig(TypedDict):
    guilds: list[int]
    channels: list[int]


class HangarConfig(TypedDict):
    guilds: list[int]


class Config(TypedDict):
    app: AppConfig
    proposals: ProposalsConfig
    events: EventsConfig
    hangar: HangarConfig


def load_config() -> Config:
    """Load the configuration from the appropriate TOML file based on the environment."""

    path = "config.toml" if PYTHON_ENV == "production" else "config.dev.toml"

    with open(path, "rb") as f:
        return tomllib.load(f)


config: Config = load_config()
