from pmg.m11_invoice import Invoice


def test_total():
    assert Invoice(lines=[1.5, 2.5]).total == 4.0


def test_total_ignores_input():
    assert Invoice(lines=[1, 2], total=99).total == 3
