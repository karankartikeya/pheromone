from pmg.m36_session_cache import Session


def test_private_cache():
    s = Session(user_id=1)
    s.remember("theme", "dark")
    assert s.recall("theme") == "dark"


def test_sessions_do_not_share_cache():
    a, b = Session(user_id=1), Session(user_id=2)
    a.remember("theme", "dark")
    assert b.recall("theme") is None
