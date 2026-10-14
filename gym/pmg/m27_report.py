from pmg.common import Entity
from pmg.m05_customer_export import Customer


class Report(Entity):
    owner: Customer
    rows: int = 0


def summary(r: Report) -> dict:
    return r.dict(include={"id", "rows"})
