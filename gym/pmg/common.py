from datetime import datetime, timezone

from pydantic import BaseModel


class Timestamped(BaseModel):
    created_at: datetime = datetime(2024, 1, 1, tzinfo=timezone.utc)

    class Config:
        json_encoders = {datetime: lambda d: d.strftime("%Y-%m-%d")}

    def to_record(self) -> dict:
        return self.dict(exclude_none=True)


class Entity(Timestamped):
    id: int
