import json
from decimal import Decimal

from pmg.m34_price_feed import Quote, publish


def test_price_is_a_json_number():
    data = json.loads(publish(Quote(symbol="ACME", price=Decimal("12.50"))))
    assert data["price"] == 12.5
