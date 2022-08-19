# type: ignore
# fmt: off

# autodoc: test_AssignVisitor on

a = 1  # type: int>>invalid
"""a docstring"""
b = 2  # type: int
"""b docstring"""
"""bad"""
def a(): ...
"""bad"""
c = d = 3
"""c and d docstring"""
x['_'], x.attr = 1, 2
"""bad"""

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

class C:
    a = 1
    """C.a docstring"""
    @classmethod  # no check
    def ma(cls, a, b):
        a = 1  # type: bad
        """bad"""
    def __init__(slf, a, b):
        self.badattr = 1  # type: int | str
        """bad"""
        slf.a = slf.b = 1  # type: str | None
        """C.__init__.a/b docstring"""
    class _A:
        _a = 1
        """bad"""

# autodoc: test_AssignVisitor off


# fmt: on
