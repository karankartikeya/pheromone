from typing import Optional

from pmg.common import Entity


class Staff(Entity):
    full_name: str
    manager_id: Optional[int] = None

    class Config:
        allow_population_by_field_name = True
        fields = {"full_name": {"alias": "fullName"}}


def from_api(raw: dict) -> Staff:
    return Staff(**raw)
