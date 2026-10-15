from decimal import Decimal

from pydantic import BaseModel


class Quote(BaseModel):
    symbol: str
    price: Decimal


def publish(q: Quote) -> str:
    return q.json()
