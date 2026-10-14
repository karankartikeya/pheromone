from pmg.m09_tag_list import parse_tags


def test_normalized():
    assert parse_tags([" B", "a", "b"]).normalized() == ["a", "b"]


def test_single():
    assert parse_tags(["x"]).normalized() == ["x"]
