from beanie import Document


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
