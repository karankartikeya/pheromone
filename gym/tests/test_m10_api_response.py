from pmg.m10_api_response import first_page


def test_coerces_items():
    assert first_page({"items": ["1", 2]}).items == [1, 2]


def test_cursor_default():
    assert first_page({"items": []}).next_cursor is None
