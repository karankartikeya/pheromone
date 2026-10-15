from typing import Union

from pydantic import BaseModel


class Lookup(BaseModel):
    key: Union[int, str]


def normalize(raw: dict) -> Lookup:
    return Lookup(**raw)
