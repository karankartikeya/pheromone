from typing import List

from pydantic import BaseModel


class Invoice(BaseModel):
    lines: List[float]
    total: float = 0.0

    def __init__(self, **data):
        super().__init__(**data)
        self.total = sum(self.lines)
