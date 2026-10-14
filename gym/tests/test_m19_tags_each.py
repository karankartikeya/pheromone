from pmg.m19_tags_each import Post


def test_each_item():
    assert Post(tags=[" A", "b "]).tags == ["a", "b"]
