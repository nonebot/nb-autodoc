from typing import Literal, Set
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
comment_ahead: Literal["e"]

comment_after: Literal["f"]
#: comment after
#: --connect

comment_inline: Literal["g"]  #: comment inline

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
    def dummyping(self) -> Literal["dummyping"]: ...
    def __getattr__(self, name: str) -> str: ...
