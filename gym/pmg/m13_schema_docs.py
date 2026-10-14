from pydantic import BaseModel, Field


class Address(BaseModel):
    street: str = Field(..., description="Street and number")
    zip_code: str


def documented_fields() -> dict:
    props = Address.schema()["properties"]
    return {k: v.get("description", "") for k, v in props.items()}
