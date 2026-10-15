from pmg.m29_lookup_key import normalize


def test_numeric_strings_become_ints():
    assert normalize({"key": "42"}).key == 42


def test_words_stay_strings():
    assert normalize({"key": "abc"}).key == "abc"
