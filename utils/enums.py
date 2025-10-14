from enum import Enum


class EventStatus(Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ProposalStatus(Enum):
    ACTIVE = "active"
    CLOSED = "closed"
