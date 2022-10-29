# type: ignore
# fmt: off

import os
from pathlib import Path

# give module and package name for DefinitionFinder to analyze following import stmt
from mypkg import ext_A, ext_fa
from mypkg.pkg import ext_B, ext_fb

from .util import ext_fc

a = 1  # type: int
"""a docstring"""
a2 = 1  # type: int
a3: "A" = 1
b = 2  # type: int
"""b docstring"""
"""bad"""
def fa(): ...
"""bad"""
c = d = 3
"""c and d docstring"""
x['_'], x.attr = 1, 2
"""no new variable so bad"""

(
    x['_'], (a1, b1)
) = (
    c1, (d1, e1)
) = 1, (2, 3)
"""abcde11111 docstring"""

class A:
    a = 1

class B:
    a = 1
    """B.a docstring"""

class B1:
    a = 1
    # no self check, and no staticmethod check
    def __init__(): ...
    @staticmethod
    def b(arg):
        # treat as instance var, but no visitor for it
        arg.a = 1
        a = 1  # type: bad
        """bad"""

class C:
    a = 1
    """C.a classvar docstring"""
    def __init__(slf, a, b):
        self.badattr1: int = 1
        self.badattr2 = 1  # type: bad
        """bad"""
        slf.a = slf.b = 1  # type: int | None
        """C instance var a/b docstring"""
        slf.c: int = 1
        slf.d: str = 'foo'
        """C instance var d docstring"""
    class _A:
        _a = 1
        """nested OK"""
