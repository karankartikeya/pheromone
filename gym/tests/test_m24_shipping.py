from pmg.m24_shipping import Shipment


def test_fee_default():
    assert Shipment(weight_kg=3).fee == 5.0


def test_express():
    assert Shipment(weight_kg=1, express=True).fee == 6.0
