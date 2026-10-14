from pydantic import BaseModel, validator


class OrderLine(BaseModel):
    quantity: int
    unit_price: float
    total: float = 0.0

    @validator("total", always=True)
    def compute_total(cls, v, values):
        return round(values["quantity"] * values["unit_price"], 2)
