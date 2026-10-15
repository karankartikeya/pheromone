import json

from pmg.m35_shift_log import Shift, to_wire


def test_utc_offset_format():
    data = json.loads(to_wire(Shift(worker="kim", started="2024-03-01T08:00:00+00:00")))
    assert data["started"] == "2024-03-01T08:00:00+00:00"
