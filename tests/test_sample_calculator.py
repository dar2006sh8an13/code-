"""Unit tests for sample calculator."""

import pytest
from sample_calculator import divide_numbers


def test_divide_normal() -> None:
    """Verify normal division."""
    assert divide_numbers(20.0, 4.0) == 5.0


def test_divide_by_zero() -> None:
    """Verify zero division returns 0."""
    assert divide_numbers(10.0, 0.0) == 0.0

