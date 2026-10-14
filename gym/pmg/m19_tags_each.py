from typing import List

from pydantic import BaseModel, validator


class Post(BaseModel):
    tags: List[str]

    @validator("tags", each_item=True)
    def lower(cls, v):
        return v.strip().lower()
