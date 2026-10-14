import pytest
from pydantic import ValidationError

from pmg.m01_signup import Signup


def test_matching_passwords():
    s = Signup(email="a@b.c", password="x1", password_confirm="x1")
    assert s.password_confirm == "x1"


def test_mismatch_rejected():
    with pytest.raises(ValidationError):
        Signup(email="a@b.c", password="x1", password_confirm="x2")
