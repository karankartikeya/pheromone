from pydantic import Field

from pmg.common import Timestamped


class Event(Timestamped):
    event_type: str = Field(..., alias="type")
    payload: dict = {}


def to_wire(e: Event) -> str:
    return e.json(by_alias=True)
