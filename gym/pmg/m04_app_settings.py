from pydantic import BaseSettings


class AppSettings(BaseSettings):
    debug: bool = False
    workers: int = 2

    class Config:
        env_prefix = "GYM_"


def load() -> AppSettings:
    return AppSettings()
