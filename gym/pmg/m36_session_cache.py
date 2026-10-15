from pydantic import BaseModel


class Session(BaseModel):
    user_id: int
    _cache: dict = {}

    class Config:
        underscore_attrs_are_private = True

    def remember(self, key: str, value: str) -> None:
        self._cache = {**self._cache, key: value}

    def recall(self, key: str):
        return self._cache.get(key)
