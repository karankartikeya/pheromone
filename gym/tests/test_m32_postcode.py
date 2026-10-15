import pytest
from pydantic import ValidationError

from pmg.m32_postcode import Delivery


def test_normalizes():
    assert Delivery(post_code=" 10 115").post_code == "10115"


def test_rejects():
    with pytest.raises(ValidationError):
        Delivery(post_code="ABC")
