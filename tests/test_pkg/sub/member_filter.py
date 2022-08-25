# test by test_inspector::test_member_filter given package "test_pkg.sub"
import os
from pathlib import Path

from click import Argument, Context

from .. import api
from ..api import Api  # supermodule but not in document
from . import _reexport_sample
from ._reexport_sample import fa  # same-level object but not from current module

# variable is documented by keeping docstring
a: int = 1

b: int = 1
"""taken"""

_a: int = 1

_b: int = 1
"""taken"""


def fa() -> None:
    """fa takes first order because fa overrides _reexport_sample.fa"""


def _fa() -> None:
    ...


def _fb() -> None:
    ...


def _gen_dynamic_func(override=""):
    def a():
        pass

    if override:
        a.__qualname__ = override

    return a


fb_dynamic = _gen_dynamic_func()  # warning not correct qualname
_fc_dynamic = _gen_dynamic_func()  # no warning for not documented
"""not taken even though function is var assign and has docstring."""
_fd_dynamic = _gen_dynamic_func()  # warning not correct qualname
"""But this override _fd.docstring"""
fd_dynamic = _gen_dynamic_func("fd_dynamic")  # no warning


def _gen_dynamic_class(override=""):
    class A:
        ...

    return A


# The test autodoc should only contain current module member
# to avoid create any External or LibraryAttr
__autodoc__ = {"_fb": True, "_fd_dynamic": True}
