from datetime import datetime

import discord
from beanie import Document
from pydantic import BaseModel, Field

from utils.enums import ProposalStatus


class Votes(BaseModel):
    """Embedded document for storing votes on a proposal."""

    upvotes: list[str] = Field(default_factory=list)
    downvotes: list[str] = Field(default_factory=list)


class Proposal(Document):
    """Beanie document model for proposals."""

    thread_id: str
    message_id: str
    creator_id: str
    created_at: datetime = Field(default_factory=discord.utils.utcnow)
    status: ProposalStatus = Field(default=ProposalStatus.ACTIVE)
    votes: Votes = Field(default_factory=Votes)

    class Settings:
        name = "proposals"
        indexes = [
            "thread_id",
            "created_at",
            "status",
        ]
