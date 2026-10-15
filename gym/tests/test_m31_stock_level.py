from pmg.m31_stock_level import from_sensor


def test_fractional_reading_truncates():
    assert from_sensor("B1", 12.8).units == 12


def test_whole_reading():
    assert from_sensor("B1", 7.0).units == 7
