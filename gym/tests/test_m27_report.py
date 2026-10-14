from pmg.m27_report import Report, summary


def test_summary():
    r = Report(id=9, owner={"id": 1, "name": "Ada"}, rows=4)
    assert summary(r) == {"id": 9, "rows": 4}
