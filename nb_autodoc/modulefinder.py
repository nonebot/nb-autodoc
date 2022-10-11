"""Module finder find all submodules recursively.

This will never involve the import system and always use `importlib.import_module` to
perform import. `ImportError` raises properly.

Directory or module name that not an identifier will not be imported. Those are thinked
as other module's search path.
"""

import inspect
import os
import sys
import types
from dataclasses import dataclass
from fnmatch import fnmatchcase
from importlib import import_module
from importlib.machinery import SourceFileLoader, all_suffixes
from importlib.util import module_from_spec, spec_from_loader
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Final,
    Iterable,
    Iterator,
    List,
    final,
)

from nb_autodoc.log import logger
from nb_autodoc.utils import frozendict

if TYPE_CHECKING:
    from nb_autodoc.config import Config

if sys.version_info < (3, 11):
    from importlib._bootstrap_external import _NamespaceLoader as NamespaceLoader
else:
    from importlib.machinery import NamespaceLoader


_Filter = Callable[[str], bool]


# Package and its __init__ global namespace is thinked as same thing.
# The introspection should always skip the <module> attributes.
@dataclass
class ModuleProperties:
    """Module properties."""

    module: types.ModuleType

    # this is portions in Namespace
    submodules: Dict[str, "ModuleProperties"]

    @property
    def name(self) -> str:
        return self.module.__name__

    # @property
    # def package(self) -> Optional[str]:
    #     return self.module.__package__

    @property
    def modname(self) -> str:
        return self.name.rpartition(".")[2]

    # @property
    # def is_c_module(self) -> bool:
    #     # generic EXTENSION suffix
    #     return self.suffix.endswith(".so")


_special_exclude_dirs = [
    "__pycache__",
    "site-packages",
    "__pypackage__",
    "node_modules",
]

_special_exclude_modulename = ["__init__", "__main__"]


class _Finder:
    """Base class provides filter."""

    @final
    def __init__(self, config: "Config") -> None:
        ...

    @final
    @staticmethod
    def _build_filter(*patterns: str) -> _Filter:
        return lambda x: any(fnmatchcase(x, pt) for pt in patterns)


SOURCE_SUFFIXES: Final[List[str]] = [".py", ".pyi"]


def create_module_from_sourcefile(
    modulename: str, path: str, init_attrs: Dict[str, Any] = frozendict()
) -> types.ModuleType:
    """Create module from source file, this is useful for executing ".pyi" file.

    `importlib` supports suffixes like ".so" (extension_suffixes),
    ".py" (source_suffixes), ".pyc" (bytecode_suffixes).
    These extensions are recorded in `importlib._bootstrap_external`.
    """
    modname, ext = os.path.splitext(os.path.basename(path))
    if not ext in SOURCE_SUFFIXES:
        raise ValueError(
            f"expect suffixes {SOURCE_SUFFIXES} to create source file module, "
            f"got {path!r} with suffix {ext!r}"
        )
    loader = SourceFileLoader(modulename, path)
    # spec_from_file_location without loader argument will skip invalid file extension
    spec = spec_from_loader(modulename, loader, is_package=modname == "__init__")
    if spec is None:  # only for type hints
        raise ImportError("no spec found", name=modulename, path=path)
    module = module_from_spec(spec)
    # exec after init namespace from TYPE_CHECKING
    module.__dict__.update(init_attrs)
    loader.exec_module(module)
    return module


def _looks_like_package(path: str) -> bool:
    try:
        dircontents = os.listdir(path)
    except OSError:
        dircontents = []
    for fn in dircontents:
        left, dot, right = fn.partition(".")
        if dot and left == "__init__" and "." + right in all_suffixes() + [".pyi"]:
            # we generally allow pyi if package is stub for .so file
            return True
    # return os.path.isfile(os.path.join(path, "__init__.py"))
    return False


class SourceModuleFinder(_Finder):
    """Module finder for package `__path__`."""

    # _LoaderBasics.is_package should be mock though compat

    def iter_modules(
        self, fullname: str, path: Iterable[str]
    ) -> Iterator[types.ModuleType]:
        # # check because find_spec on NamespacePath wants package __path__
        # assert fullname in sys.modules, f"module {fullname} must be imported"
        namespace_path: List[str] = []
        for entry in path:
            try:
                dircontents = os.listdir(entry)
            except OSError:
                continue  # skip unreadable path
            for item in dircontents:
                itempath = os.path.join(entry, item)
                if os.path.isfile(itempath):
                    modname, ext = os.path.splitext(item)
                    if (
                        modname.isidentifier()
                        and modname not in _special_exclude_modulename
                        and ext in SOURCE_SUFFIXES
                    ):
                        yield import_module(fullname + "." + modname)
                elif os.path.isdir(itempath):
                    if not item.isidentifier() or item in _special_exclude_dirs:
                        continue
                    if _looks_like_package(itempath):
                        pkg = import_module(fullname + "." + item)
                    # package has __init__.pyi
                    modname = inspect.getmodulename(item) or ""
                    # is package, import and get __path__
                    if modname.isidentifier():
                        continue
                    # is implicit namespace, record it but not import
            # If no source file found under namespace package
            # c extension maybe bound with pyi directory
            # pyi must have a truly module, but finder do not analysis
        # if namespace path, call iter_modules
        if namespace_path:
            yield from self.iter_modules(
                fullname + "." + os.path.basename(namespace_path[0]), namespace_path
            )
