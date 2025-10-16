from datetime import datetime

import discord
from beanie import Document
from pydantic import BaseModel, Field

from utils.enums import EventStatus


class LootItem(BaseModel):
    """Embedded document for storing loot items in an event."""

    id: str
    name: str


class LootEntry(BaseModel):
    """Embedded document for storing loot entries in an event."""

    item: LootItem
    quantity: int
    added_by: str
    added_at: datetime = Field(default_factory=discord.utils.utcnow)


class Event(Document):
    """Beanie document model for events."""

    thread_id: str
    message_id: str
    creator_id: str
    created_at: datetime = Field(default_factory=discord.utils.utcnow)
    name: str
    description: str
    status: EventStatus = Field(default=EventStatus.ACTIVE)
    participants: list[str] = Field(default_factory=list)
    loot_entries: list[LootEntry] = Field(default_factory=list)

    class Settings:
        name = "events"
        indexes = [
            "thread_id",
            "creator_id",
            "created_at",
            "status",
        ]
