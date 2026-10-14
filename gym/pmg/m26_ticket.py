from enum import Enum

from pydantic import BaseModel, validator


class Priority(str, Enum):
    low = "low"
    high = "high"


class Ticket(BaseModel):
    title: str
    priority: Priority = Priority.low
    escalated: bool = False

    @validator("escalated", always=True)
    def escalate_high(cls, v, values):
        return v or values.get("priority") == Priority.high

    class Config:
        use_enum_values = True
        anystr_strip_whitespace = True
