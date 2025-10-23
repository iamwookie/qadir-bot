from enum import Enum


class ProposalStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class EventStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class HangarStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
