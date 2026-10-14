from pmg.m13_schema_docs import documented_fields


def test_descriptions():
    assert documented_fields()["street"] == "Street and number"


def test_all_fields_listed():
    assert set(documented_fields()) == {"street", "zip_code"}
