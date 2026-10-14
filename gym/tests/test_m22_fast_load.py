from pmg.m22_fast_load import trusted


def test_no_validation():
    m = trusted([{"name": "cpu", "value": "not-a-float"}])[0]
    assert m.value == "not-a-float"
