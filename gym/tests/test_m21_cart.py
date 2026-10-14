import pytest
from pydantic import ValidationError

from pmg.m21_cart import Cart


def test_ok():
    assert Cart(item_ids=[1, 2]).item_ids == [1, 2]


def test_empty_rejected():
    with pytest.raises(ValidationError):
        Cart(item_ids=[])
