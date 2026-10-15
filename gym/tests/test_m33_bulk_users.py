from pmg.m33_bulk_users import load_users


def test_bulk():
    users = load_users([{"id": "1", "email": "a@b.c"}, {"id": 2, "email": "d@e.f"}])
    assert [u.id for u in users] == [1, 2]
