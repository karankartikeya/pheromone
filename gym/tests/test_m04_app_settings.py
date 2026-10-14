from pmg.m04_app_settings import load


def test_defaults(monkeypatch):
    monkeypatch.delenv("GYM_WORKERS", raising=False)
    assert load().workers == 2


def test_env_prefix(monkeypatch):
    monkeypatch.setenv("GYM_WORKERS", "8")
    assert load().workers == 8
