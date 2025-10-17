from beanie import Document



class HangarEmbed(Document):
    """Beanie document model for hangar embeds."""

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