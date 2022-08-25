# type: ignore
# fmt: off

# autodoc: test_VariableVisitor on

a = 1  # type: int
"""a docstring"""
a2 = 1  # type: int
a3: "A" = 1
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
        self.badattr1: int = 1
        self.badattr2 = 1  # type: bad
        """bad"""
        slf.a = slf.b = 1  # type: str | None
        """C.__init__.a/b docstring"""
        slf.c: int = 1
        slf.d: str = 'foo'
        """C.__init__.d docstring"""
    class _A:
        _a = 1
        """bad"""

# autodoc: test_VariableVisitor off


# fmt: on
