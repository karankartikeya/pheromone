from pmg.m07_import_rows import import_rows


def test_import():
    products = import_rows([{"sku": "A1", "price": "9.5"}])
    assert products[0].price == 9.5


def test_import_many():
    assert len(import_rows([{"sku": "A", "price": 1}, {"sku": "B", "price": 2}])) == 2
