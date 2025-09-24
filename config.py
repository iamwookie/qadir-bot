import os
from typing import TypedDict

import tomllib
from dotenv import load_dotenv

DISCORD_TOKEN: str = os.environ["DISCORD_TOKEN"]  # type: ignore
UPSTASH_REDIS_REST_URL: str = os.environ["UPSTASH_REDIS_REST_URL"]  # type: ignore
UPSTASH_REDIS_REST_TOKEN: str = os.environ["UPSTASH_REDIS_REST_TOKEN"]  # type: ignore


class AppConfig(TypedDict):
    version: str
    debug: bool


class ProposalsConfig(TypedDict):
    guilds: list[int]
    channels: list[int]
    roles: list[int]


class Config(TypedDict):
    app: AppConfig
    proposals: ProposalsConfig


def load_config() -> Config:
    """Load the configuration from the appropriate TOML file based on the environment."""

    load_dotenv(override=False)

    path = "config.toml" if os.getenv("PYTHON_ENV") == "production" else "config.dev.toml"

    with open(path, "rb") as f:
        return tomllib.load(f)


config: Config = load_config()
