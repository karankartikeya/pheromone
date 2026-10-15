from typing import Optional

from pydantic import BaseModel


class ProfilePatch(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None


def changed_fields(raw: dict) -> list:
    return sorted(ProfilePatch(**raw).__fields_set__)
