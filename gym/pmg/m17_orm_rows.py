from dataclasses import dataclass

from pydantic import BaseModel


@dataclass
class BookRow:
    id: int
    title: str


class Book(BaseModel):
    id: int
    title: str

    class Config:
        orm_mode = True


def load(rows) -> list:
    return [Book.from_orm(r) for r in rows]
