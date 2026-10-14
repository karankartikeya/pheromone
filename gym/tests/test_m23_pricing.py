from pmg.m23_pricing import discounted


def test_coerces():
    assert discounted("10", "50") == 5.0
