from pathlib import Path

from ._sample import A, _fc, _fd, _fe, fa, fb
from .inter import inter_A
from .inter import inter_A as reexport_inter_A

__autodoc__ = {
    "fa": True,
    "_fc": True,  # tell submodule "_sample" to whitelist it
    "A": True,
    "A.fa": False,  # tell class A to blacklist it
    "A._fc": True,  # tell class A to whitelist it
    "Path": "stdlib pathlib.Path docstring...",
    "inter_A": True,
    "reexport_inter_A": True,
}
