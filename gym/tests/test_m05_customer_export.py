from pmg.m05_customer_export import Customer, export


def test_export_drops_none():
    rows = export([Customer(id=1, name="Ada")])
    assert rows[0]["name"] == "Ada"
    assert "vat_id" not in rows[0]


def test_export_keeps_values():
    rows = export([Customer(id=2, name="Bo", vat_id="DE1")])
    assert rows[0]["vat_id"] == "DE1"
