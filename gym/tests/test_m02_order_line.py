from pmg.m02_order_line import OrderLine


def test_total_computed():
    assert OrderLine(quantity=3, unit_price=2.5).total == 7.5


def test_total_overrides_input():
    assert OrderLine(quantity=2, unit_price=1.0, total=99).total == 2.0
