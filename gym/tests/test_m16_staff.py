from pmg.m16_staff import Staff, from_api


def test_alias():
    assert from_api({"id": 1, "fullName": "Kim"}).full_name == "Kim"


def test_field_name_allowed():
    assert Staff(id=2, full_name="Lee").full_name == "Lee"
