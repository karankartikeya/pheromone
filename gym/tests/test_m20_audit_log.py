import json

from pmg.m20_audit_log import AuditEntry, serialize


def test_dates_encoded():
    out = serialize([AuditEntry(actor="ops", at="2024-05-06T10:00:00")])
    assert json.loads(out[0])["at"] == "2024-05-06"
