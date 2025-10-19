from datetime import datetime

import discord
from beanie import Document, Insert, before_event
from pydantic import BaseModel, Field


class PartialActivity(BaseModel):
    """Embedded document for storing partial activity data."""

    user_id: str
    activity: str
    start_time: datetime = Field(default_factory=discord.utils.utcnow)


class Activity(Document):
    """Beanie document model for activity data."""

    user_id: str
    activity: str
    start_time: datetime
    end_time: datetime = Field(default_factory=discord.utils.utcnow)
    duration: float = 0.0

    @before_event(Insert)
    def set_duration(self):
        self.duration = (self.end_time - self.start_time).total_seconds()

    class Settings:
        name = "activity_data"
