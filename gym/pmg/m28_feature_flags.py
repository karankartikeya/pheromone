from typing import Dict

from pydantic import BaseModel, Extra


class Flags(BaseModel):
    beta: bool = False

    class Config:
        extra = Extra.allow


def enabled(raw: Dict[str, bool]) -> list:
    flags = Flags(**raw)
    return sorted(k for k, v in flags.dict().items() if v)
