# type: ignore
from typing import overload


a = 1
"""a docstring"""


@overload
def b():
    ...


b = 1
"""b docstring"""


class A:
    a = 1
    """A.a docstring"""
