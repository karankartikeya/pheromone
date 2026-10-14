import pytest
from pydantic import ValidationError

from pmg.m18_product_code import Item


def test_valid():
    assert Item(code="ABC-123").code == "ABC-123"


def test_invalid():
    with pytest.raises(ValidationError):
        Item(code="abc")
