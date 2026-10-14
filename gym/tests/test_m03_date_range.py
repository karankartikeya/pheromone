import pytest
from pydantic import ValidationError

from pmg.m03_date_range import DateRange


def test_days():
    assert DateRange(start="2024-01-01", end="2024-01-11").days == 10


def test_reversed_rejected():
    with pytest.raises(ValidationError):
        DateRange(start="2024-02-01", end="2024-01-01")
