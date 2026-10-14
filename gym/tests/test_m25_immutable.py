import pytest

from pmg.m25_immutable import EUR, Currency


def test_frozen():
    with pytest.raises((TypeError, ValueError)):
        EUR.code = "USD"


def test_equal_by_value():
    assert Currency(code="EUR") == EUR
