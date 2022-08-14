from contextvars import ContextVar
from typing import overload

from .typing import T_Type

@overload
def func(arg: ContextVar[int]) -> T_Type:
    """
    docstring overload 1.

    Args:
        arg: the context var of type int.

    Returns:
        T_Type: str or none.
    """
    ...

@overload
def func(arg: int) -> int:
    """
    docstring overload 2.

    Args:
        arg: the primitive type int parameter.

    Returns:
        int: the calculated arg.
    """
    ...

class A:
    @overload
    def foo(self, s: T_Type) -> str: ...
    @overload
    def foo(self, s: str) -> str: ...
