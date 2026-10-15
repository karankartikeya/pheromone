from pmg.m38_patch_request import changed_fields


def test_only_sent_fields():
    assert changed_fields({"bio": None}) == ["bio"]
