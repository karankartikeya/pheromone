from pmg.m30_sku_label import from_row


def test_numeric_sku_is_text():
    assert from_row({"sku": 10045, "title": "Lamp"}).sku == "10045"
