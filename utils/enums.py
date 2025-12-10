from enum import Enum


class ProposalStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class HangarStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
