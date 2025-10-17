import discord

from datetime import datetime

from beanie import Document
from pydantic import BaseModel, Field, computed_field


class PartialActivity(BaseModel):
    """Embedded document for storing partial activity data."""

    user_id: str
    activity: str
    start_time: datetime = Field(default_factory=discord.utils.utcnow)


class Activity(Document):
    """Beanie document model for activities."""

    user_id: str
    activity: str
    start_time: datetime
    end_time: datetime = Field(default_factory=discord.utils.utcnow)

    @computed_field
    @property
    def duration(self) -> float:
        return (self.end_time - self.start_time).total_seconds()

    class Settings:
        name = "activities"
        indexes = [
            "user_id",
            "activity",
            "start_time",
            "end_time",
        ]
