import os
import sys
from contextlib import contextmanager
from importlib import import_module
from typing import Tuple, Union


@contextmanager
def uncache_import(path: Union[str, Tuple[str, ...]], module: str):
    """Insert path and import module. Note module must not be a dependent module."""
    if isinstance(path, str):
        path = (path,)
    path = tuple(os.path.abspath(os.path.normpath(i)) for i in path)
    saved_path = sys.path.copy()
    sys.path[:0] = path
    try:
        yield import_module(module)
    finally:
        sys.path[:] = saved_path
        del sys.modules[module]
        subnames = [i for i in sys.modules if i.startswith(module + ".")]
        for name in subnames:
            del sys.modules[name]
