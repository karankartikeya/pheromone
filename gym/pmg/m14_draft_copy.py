from pydantic import BaseModel


class Draft(BaseModel):
    title: str
    version: int = 1


def bump(d: Draft) -> Draft:
    return d.copy(update={"version": d.version + 1})
