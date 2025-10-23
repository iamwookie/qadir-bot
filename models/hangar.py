from datetime import datetime

from beanie import Document
from pydantic import BaseModel

from utils.enums import HangarStatus


class HangarState(BaseModel):
    """Model representing the hangar state information."""

    status: HangarStatus
    color: int
    lights: list[str]
    next_status_change: datetime
    next_light_change: datetime


class HangarEmbedItem(Document):
    """Beanie document model for hangar embed data."""

    message_id: str
    channel_id: str
    guild_id: str

    class Settings:
        name = "hangar_embeds"
        indexes = [
            "message_id",
            "channel_id",
            "guild_id",
        ]
