from typing import Callable, Set
from contextvars import ContextVar

from test_pkg.pyi.util import func_forimport, T_Checktyping

# ERROR: from .util import func_forimport

var: ContextVar[int] = ...

var2: int = ...
"""var2 override docstring"""

var3: T_Checktyping = ...
"""var3 override docstring"""

#: connect--
#: comment ahead
comment_ahead: int

comment_after: Set[int]
#: comment after
#: --connect

comment_inline: Callable[[], int]  #: comment inline

def func(arg: int) -> T_Checktyping: ...

class A:
    pinged: Set[str]
    """inst attr pinged"""
    b: int
    """blacklisted attr b"""
    c: int = 4
    """A's attr C"""
    def __init__(self) -> None:
        self.x = 1
        """self.x docstring"""
    def ping(self, name: str) -> str: ...
    def pingelse(self, name: str = ...) -> str:
        """pingelse override docstring"""
        ...
    @property
    def dummyping(self) -> str: ...
    def __getattr__(self, name: str) -> str: ...
