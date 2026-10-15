from pmg.m37_api_docs import example


def test_example_in_schema():
    assert example() == {"sku": "A-100", "quantity": 2}
