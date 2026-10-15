from pydantic import BaseModel


class CreateOrder(BaseModel):
    sku: str
    quantity: int

    class Config:
        schema_extra = {"example": {"sku": "A-100", "quantity": 2}}


def example() -> dict:
    return CreateOrder.schema()["example"]
