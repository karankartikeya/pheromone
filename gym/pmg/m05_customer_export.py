from typing import Optional

from pmg.common import Entity


class Customer(Entity):
    name: str
    vat_id: Optional[str] = None


def export(customers: list) -> list:
    return [c.to_record() for c in customers]
