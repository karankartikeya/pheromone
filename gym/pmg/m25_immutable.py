from pydantic import BaseModel


class Currency(BaseModel):
    code: str
    decimals: int = 2

    class Config:
        allow_mutation = False


EUR = Currency(code="EUR")
