from typing import Optional

from pydantic import BaseModel, root_validator


class Shipment(BaseModel):
    weight_kg: float
    express: bool = False
    fee: Optional[float] = None

    @root_validator(pre=True)
    def default_fee(cls, values):
        if values.get("fee") is None:
            base = 5.0 if values.get("express") else 2.0
            values["fee"] = base + float(values.get("weight_kg", 0))
        return values
