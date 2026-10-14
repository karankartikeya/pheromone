from pydantic import BaseModel


class Product(BaseModel):
    sku: str
    price: float


def import_rows(rows: list) -> list:
    return [Product.parse_obj(r) for r in rows]
