from pathlib import Path

from ._reexport_sample import A, _fc, _fd, _fe, fa, fb

__autodoc__ = {
    "fa": True,
    "_fc": True,
    "A": True,
    "A.a": False,
    "A._c": True,
    "Path": "pathlib.Path docstring...",
}
