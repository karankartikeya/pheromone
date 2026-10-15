from pydantic import BaseModel


class Label(BaseModel):
    sku: str
    title: str


def from_row(row: dict) -> Label:
    return Label(**row)
