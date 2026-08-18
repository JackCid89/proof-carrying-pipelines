from calc import add, safe_div
import pytest

def test_add():
    assert add(2, 3) == 5

def test_safe_div():
    assert safe_div(6, 3) == 2
    with pytest.raises(ValueError):
        safe_div(1, 0)
