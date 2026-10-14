from pydantic import BaseModel


class Metric(BaseModel):
    name: str
    value: float


def trusted(rows: list) -> list:
    return [Metric.construct(**r) for r in rows]
