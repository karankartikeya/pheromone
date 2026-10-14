from typing import Optional

from pydantic import BaseModel


class ContactForm(BaseModel):
    name: str
    phone: Optional[str] = None
    message: str


def required_fields(model=ContactForm) -> list:
    return [name for name, f in model.__fields__.items() if f.required]
