from datetime import datetime

from pmg.common import Timestamped


class AuditEntry(Timestamped):
    actor: str
    at: datetime


def serialize(entries: list) -> list:
    return [e.json() for e in entries]
