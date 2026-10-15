from pydantic import BaseModel


class StockLevel(BaseModel):
    warehouse: str
    units: int


def from_sensor(warehouse: str, reading: float) -> StockLevel:
    return StockLevel(warehouse=warehouse, units=reading)
