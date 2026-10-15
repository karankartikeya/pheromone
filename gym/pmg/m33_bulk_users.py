from typing import List

from pydantic import BaseModel, parse_obj_as


class User(BaseModel):
    id: int
    email: str


def load_users(rows: list) -> List[User]:
    return parse_obj_as(List[User], rows)
