from contextvars import ContextVar

from test_pkg.pyi.util import func_forimport, T_Checktyping


var = ContextVar("var", default=4)
"""context var without anno"""

var2: int = 1
"""var2 should be replaced docstring"""

var3: T_Checktyping
"""only annotation variable in real module"""

comment_ahead = "e"

comment_after = "f"

comment_inline = "g"


def func(arg):
    """dummy func"""
    return 1


class A:
    """class A"""

    def __init__(self):
        super().__init__()

    def ping(self, name):
        """generic ping"""
        setattr(self, name, f"{name} is pinged")
        return name

    def pingelse(self, name="else"):
        """special ping, should be replaced docstring"""
        return name

    def __getattr__(self, name):
        if name == "dummyping":
            return self.pingelse(name)
        return self.ping(name)


__pdoc__ = {"A.b": False}
