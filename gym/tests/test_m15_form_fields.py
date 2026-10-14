from pmg.m15_form_fields import required_fields


def test_required():
    assert required_fields() == ["name", "message"]
