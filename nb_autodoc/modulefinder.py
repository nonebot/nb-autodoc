"""Module finder find all submodules recursively.

This will never involve the import system and always use `importlib.import_module` to
perform import. `ImportError` raises properly.

Directory or module name that not an identifier will not be imported. Those are thinked
as other module's search path.
"""

import os
import sys
import types
from collections import defaultdict
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
    Iterable,
    Iterator,
    List,
    Set,
    final,
)

from nb_autodoc.log import logger
from nb_autodoc.utils import frozendict, getmodulename

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


def create_module_from_sourcefile(
    modulename: str, path: str, init_attrs: Dict[str, Any] = frozendict()
) -> types.ModuleType:
    """Create module from ".py" or ".pyi" source file.

    importlib machinery supports suffixes ".so" (extension_suffixes),
    ".py" (source_suffixes), ".pyc" (bytecode_suffixes).
    """
    modname, ext = os.path.splitext(os.path.basename(path))
    if not ext in (".py", ".pyi"):
        raise ValueError(
            "expect suffixes '.py' or '.pyi' to create source file module, "
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
    for fn in os.listdir(path):
        left, dot, right = fn.partition(".")
        if dot and left == "__init__" and "." + right in all_suffixes():
            return True
    # return os.path.isfile(os.path.join(path, "__init__.py"))
    return False


class ModuleFinder(_Finder):
    """Module finder for package `__path__`."""

    def iter_modules(
        self, fullname: str, path: Iterable[str]
    ) -> Iterator[types.ModuleType]:
        # # check because find_spec on NamespacePath wants package __path__
        # assert fullname in sys.modules, f"module {fullname} must be imported"
        yielded: Set[str] = set()  # yielded item name
        namespace_path: defaultdict[str, List[str]] = defaultdict(list)
        for entry in path:
            # generally allow OSError
            dircontents = list(os.scandir(entry))
            # package before same-named module
            dircontents.sort(key=os.DirEntry.is_file)
            for itementry in dircontents:
                item = itementry.name
                if itementry.is_dir():
                    if item in yielded:
                        continue
                    if not item.isidentifier() or item in _special_exclude_dirs:
                        continue
                    # is package, import and get __path__
                    if _looks_like_package(itementry.path):
                        subfullname = fullname + "." + item
                        pkg = import_module(subfullname)
                        yield pkg
                        yielded.add(item)
                        yield from self.iter_modules(subfullname, pkg.__path__)
                    # is implicit namespace, record it but not import
                    else:
                        namespace_path[item].append(itementry.path)
                elif itementry.is_file():
                    modname = getmodulename(item)
                    if modname in yielded:
                        continue
                    if not modname or modname in _special_exclude_modulename:
                        continue
                    yield import_module(fullname + "." + modname)
                    yielded.add(modname)
        # search portions in namespace_path
        for item, path in namespace_path.items():
            if item in yielded:
                continue
            if path:
                yield from self.iter_modules(fullname + "." + item, path)
