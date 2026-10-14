from typing import Generic, List, Optional, TypeVar

from pydantic.generics import GenericModel

T = TypeVar("T")


class Page(GenericModel, Generic[T]):
    items: List[T]
    next_cursor: Optional[str] = None


def first_page(raw: dict) -> Page[int]:
    return Page[int].parse_obj(raw)
