from enum import Enum


class EventStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ProposalStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"
