from pydantic import BaseModel, conlist


class Cart(BaseModel):
    item_ids: conlist(int, min_items=1, max_items=5)
