from pydantic import BaseModel


class Webhook(BaseModel):
    url: str
    secret: str


def from_body(body: bytes) -> Webhook:
    return Webhook.parse_raw(body)
