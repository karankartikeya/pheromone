from typing import List

from pydantic import BaseModel


class Tags(BaseModel):
    __root__: List[str]

    def normalized(self) -> List[str]:
        return sorted({t.strip().lower() for t in self.__root__})


def parse_tags(raw: list) -> Tags:
    return Tags.parse_obj(raw)
