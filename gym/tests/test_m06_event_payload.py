import json

from pmg.m06_event_payload import Event, to_wire


def test_alias_on_wire():
    data = json.loads(to_wire(Event(type="click")))
    assert data["type"] == "click"


def test_custom_date_encoder():
    data = json.loads(to_wire(Event(type="x")))
    assert data["created_at"] == "2024-01-01"
