"""Module finder find all submodules recursively.

This will never involve the import system and always use `importlib.import_module` to
perform import. `ImportError` raises properly.

Directory or module name that not an identifier will not be imported. Those are thinked
as other module's search path.
"""

import os
import sys
import types
import typing as t
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from fnmatch import fnmatchcase
from importlib import import_module
from importlib.machinery import ExtensionFileLoader, SourceFileLoader, all_suffixes
from importlib.util import module_from_spec, spec_from_loader

from nb_autodoc.log import logger
from nb_autodoc.utils import getmodulename

if t.TYPE_CHECKING:
    from nb_autodoc.config import Config

if sys.version_info < (3, 11):
    from importlib._bootstrap_external import _NamespaceLoader as NamespaceLoader
else:
    from importlib.machinery import NamespaceLoader


_Filter = t.Callable[[str], bool]


class _LoaderType(Enum):
    SOURCE = 0
    EXTENSION = 1
    NAMESPACE = 2
    OTHER = 3  # dynamic or bytecode


_allow_loader_type: t.List[t.Tuple[t.Any, _LoaderType]] = [
    (SourceFileLoader, _LoaderType.SOURCE),
    (ExtensionFileLoader, _LoaderType.EXTENSION),
    (NamespaceLoader, _LoaderType.NAMESPACE),
]


# Package and its __init__ global namespace is thinked as same thing.
# The introspection should always skip the <module> attributes.
@dataclass(eq=False, frozen=True)  # to be slots
class ModuleProperties:
    """Module read-only properties."""

    # the property startswith `sm_` is special member of ModuleType
    sm_name: str
    # sm_path: t.Optional[t.List[str]]  # copied list but not Iterable
    sm_file: t.Optional[str]  # None if namespace or dynamic module
    sm_dict: types.MappingProxyType[str, t.Any]
    sm_annotations: types.MappingProxyType[str, t.Any]

    loader_type: _LoaderType

    @property
    def is_source(self) -> bool:
        return self.loader_type is _LoaderType.SOURCE

    @property
    def is_c_module(self) -> bool:
        return self.loader_type is _LoaderType.EXTENSION

    @property
    def is_namespace(self) -> bool:
        return self.loader_type is _LoaderType.NAMESPACE

    @classmethod
    def from_module(cls, module: types.ModuleType) -> "ModuleProperties":
        spec = module.__spec__
        # if spec is None:
        #     raise ValueError(f"cannot inspect dynamic module {module.__name__!r}")
        loader = spec and spec.loader
        if spec is not None and loader is None:
            raise RuntimeError(
                f"{module.__name__!r} has spec {spec} but have no loader"
            )
        if loader is None:
            loader_type = _LoaderType.OTHER
        else:
            for loader_cls, loader_type in _allow_loader_type:
                if isinstance(loader, loader_cls):
                    break
            else:
                loader_type = _LoaderType.OTHER
        return cls(
            sm_name=module.__name__,
            sm_file=module.__file__,
            sm_dict=types.MappingProxyType(module.__dict__),
            sm_annotations=types.MappingProxyType(
                getattr(module, "__annotations__", {})
            ),
            loader_type=loader_type,
        )


class _Finder:
    """Base class provides filter."""

    @t.final
    def __init__(self, config: "Config") -> None:
        ...

    @t.final
    @staticmethod
    def _build_filter(*patterns: str) -> _Filter:
        return lambda x: any(fnmatchcase(x, pt) for pt in patterns)


_special_exclude_dirs = [
    "__pycache__",
    "site-packages",
    "__pypackage__",
    "node_modules",
]

_special_exclude_modulename = ["__init__", "__main__"]


def _looks_like_package(path: str) -> bool:
    for fn in os.listdir(path):
        left, dot, right = fn.partition(".")
        if dot and left == "__init__" and "." + right in all_suffixes():
            return True
    return False


def _is_stub_package(path: str) -> bool:
    return os.path.isfile(os.path.join(path, "__init__.pyi"))


class StubFoundResult(t.NamedTuple):
    name: str
    origin: str
    is_package: bool


T_ModuleScanResult = t.Tuple[
    t.Dict[str, types.ModuleType], t.Dict[str, StubFoundResult]
]


class ModuleFinder(_Finder):
    """Search modules based on real package `__path__`."""

    def scan_modules(
        self, fullname: str, path: t.Iterable[str], ctx: T_ModuleScanResult
    ) -> T_ModuleScanResult:
        """Scan and yield modules per `__path__` recursively.

        Different from `pkgutil.iter_modules`, this function import and yield
        all submodules, and support PEP420 implicit namespace package.
        """
        # # check because find_spec on NamespacePath wants package __path__
        # assert fullname in sys.modules, f"module {fullname} must be imported"
        modules, stubs = ctx
        seen: t.Set[str] = set()  # seen item name
        namespace_path: defaultdict[str, t.List[str]] = defaultdict(list)
        for entry in path:
            # generally allow OSError
            dircontents = list(os.scandir(entry))
            # package before same-named module
            dircontents.sort(key=os.DirEntry.is_file)
            for itementry in dircontents:
                item = itementry.name
                if itementry.is_dir():
                    if _is_stub_package(itementry.path):
                        stubs[item]  # TODO
                    if item in seen:
                        continue
                    if not item.isidentifier() or item in _special_exclude_dirs:
                        continue
                    # is package, import and get __path__
                    if _looks_like_package(itementry.path):
                        module = import_module(fullname + "." + item)
                        modules[module.__name__] = module
                        seen.add(item)
                        self.scan_modules(module.__name__, module.__path__, ctx)
                    # is implicit namespace, record it but not import
                    else:
                        namespace_path[item].append(itementry.path)
                elif itementry.is_file():
                    if item.endswith(".pyi") and item[:-4].isidentifier():
                        stubs[item]  # TODO
                    modname = getmodulename(item)
                    if modname in seen:
                        continue
                    if not modname or modname in _special_exclude_modulename:
                        continue
                    module = import_module(fullname + "." + modname)
                    modules[module.__name__] = module
                    seen.add(modname)
        # search portions in namespace_path
        for item, path in namespace_path.items():
            if item in seen:
                continue
            if path:
                self.scan_modules(fullname + "." + item, path, ctx)
        return ctx

    class ModuleBoundResult(t.NamedTuple):
        module: t.Optional[ModuleProperties]
        stub: t.Optional[ModuleProperties]

    def process(self, module: types.ModuleType) -> t.Iterator[ModuleBoundResult]:
        ...


# class ModuleBoundType(Enum):
#     SOURCE_STANDALONE
#     C_EXTENSION_FILE_STUB
#     C_EXTENSION_PKG_STUB


def create_module_from_sourcefile(
    fullname: str, path: str, is_package: t.Optional[bool] = None
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
    loader = SourceFileLoader(fullname, path)
    if is_package is None:
        is_package = modname == "__init__"
    # spec_from_file_location without loader argument will skip invalid file extension
    spec = spec_from_loader(fullname, loader, is_package=is_package)
    if spec is None:  # only for type hints
        raise ImportError("no spec found", name=fullname, path=path)
    module = module_from_spec(spec)
    # maybe exec after init namespace from TYPE_CHECKING
    # but currently we disallow writing importable stmt in TYPE_CHECKING
    # module.__dict__.update(init_attrs)
    loader.exec_module(module)
    return module
