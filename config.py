import os
from typing import TypedDict

import tomllib
from dotenv import load_dotenv


class AppConfig(TypedDict):
    version: str
    debug: bool


class ProposalsConfig(TypedDict):
    guilds: list[int]
    channels: list[int]
    roles: list[int]


class LootConfig(TypedDict):
    guilds: list[int]
    channels: list[int]


class Config(TypedDict):
    app: AppConfig
    proposals: ProposalsConfig
    loot: LootConfig


def load_config() -> Config:
    """Load the configuration from the appropriate TOML file based on the environment."""
    if os.getenv("PYTHON_ENV") == "production":
        with open("config.toml", "rb") as f:
            return tomllib.load(f)
    else:
        load_dotenv(override=True)

        with open("config.dev.toml", "rb") as f:
            return tomllib.load(f)


config: Config = load_config()
