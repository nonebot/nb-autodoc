from pathlib import Path

from ._reexport_sample import A, _fc, _fd, _fe, fa, fb

__autodoc__ = {
    "fa": True,
    "_fc": True,  # tell submodule to whitelist it
    "A": True,
    "A.a": False,  # tell class A to blacklist it
    "A._c": True,  # tell class A to whitelist it
    "Path": "stdlib pathlib.Path docstring...",
}
