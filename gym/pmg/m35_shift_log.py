from datetime import datetime

from pydantic import BaseModel


class Shift(BaseModel):
    worker: str
    started: datetime


def to_wire(s: Shift) -> str:
    return s.json()
