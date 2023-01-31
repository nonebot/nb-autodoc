# type: ignore
from __future__ import annotations

from typing import overload


@overload
def func() -> str:
    """func o1"""


@overload
def func(dct: int) -> complex:
    """func o2"""


def func(dct: int = 1) -> str | complex:
    ...


@overload
def func2() -> str:
    ...


@overload
def func2(dct: int) -> complex:
    ...


func2 = _make_func2("")
"""func2 docstring"""
