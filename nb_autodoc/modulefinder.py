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
from dataclasses import dataclass, field
from enum import Enum
from fnmatch import fnmatchcase
from importlib import import_module
from importlib.machinery import ExtensionFileLoader, SourceFileLoader, all_suffixes
from importlib.util import module_from_spec, spec_from_loader
from itertools import accumulate, islice

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
    sm_doc: t.Optional[str]
    sm_package: t.Optional[str]
    sm_file: t.Optional[str]  # None if namespace or dynamic module
    sm_dict: types.MappingProxyType[str, t.Any] = field(repr=False)
    sm_annotations: types.MappingProxyType[str, t.Any] = field(repr=False)

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

    @property
    def is_package(self) -> bool:
        return "__path__" in self.sm_dict

    @classmethod
    def from_module(cls, module: types.ModuleType) -> "ModuleProperties":
        spec = module.__spec__
        # if spec is None:
        #     raise ValueError(f"cannot inspect dynamic module {module.__name__!r}")
        loader = spec and spec.loader
        if spec is not None and loader is None:
            raise RuntimeError(f"{module.__name__!r} has spec {spec} but has no loader")
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
            sm_doc=module.__doc__,
            sm_package=module.__package__,
            sm_file=getattr(module, "__file__", None),  # some module sourceless
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
        self.is_exclude_module: _Filter = _Finder._build_filter(
            config["skip_import_modules"]
        )

    @t.final
    @staticmethod
    def _build_filter(patterns: t.Iterable[str]) -> _Filter:
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


class StubFoundResult(t.NamedTuple):
    name: str
    origin: str
    is_package: bool


_ModuleScanResult = t.Tuple[t.Dict[str, types.ModuleType], t.Dict[str, StubFoundResult]]
_ModuleBoundResult = t.Tuple[
    str, t.Optional[ModuleProperties], t.Optional[ModuleProperties]
]
"""Module bound result. Tuple of module name, real module, stub module."""


class ModuleFinder(_Finder):
    """Search modules based on real package `__path__`."""

    def scan_modules(
        self, fullname: str, path: t.Iterable[str], ctx: _ModuleScanResult
    ) -> _ModuleScanResult:
        """Scan all modules from `__path__` recursively.

        Different from `pkgutil.iter_modules`, this function import and yield
        all submodules, and support PEP420 implicit namespace package.
        Namespace module is not included in result.

        This function return modules that have original file (except namespace).
        """
        # # check because find_spec on NamespacePath wants package __path__
        # assert fullname in sys.modules, f"module {fullname} must be imported"
        modules, stubs = ctx
        seen: t.Set[str] = set()  # seen item name
        seen_stubs: t.Set[str] = set()
        namespace_path: defaultdict[str, t.List[str]] = defaultdict(list)
        for entry in path:
            # generally allow OSError
            dircontents = list(os.scandir(entry))
            # package before same-named module
            dircontents.sort(key=os.DirEntry.is_file)
            for itementry in dircontents:
                item = itementry.name
                found_mod = None
                if itementry.is_dir():
                    # modname validation
                    if not item.isidentifier():
                        continue
                    # check stub
                    stub_path = os.path.join(itementry.path, "__init__.pyi")
                    if os.path.isfile(stub_path) and item not in seen_stubs:
                        childfullname = fullname + "." + item
                        stubs[childfullname] = StubFoundResult(
                            childfullname, stub_path, True
                        )
                        seen_stubs.add(item)
                        # no continue here because dir can also be real module
                    # validate and check package
                    if item in _special_exclude_dirs or item in seen:
                        continue
                    if _looks_like_package(itementry.path):
                        # is package, import and get __path__
                        found_mod = (item, True)
                    else:
                        # is implicit namespace, record it but not import
                        namespace_path[item].append(itementry.path)
                elif itementry.is_file():
                    modname: t.Optional[str]
                    # check stub roughly
                    modname, ext = os.path.splitext(item)
                    if ext == ".pyi":
                        if (
                            modname.isidentifier()
                            and modname not in _special_exclude_modulename
                            and modname not in seen_stubs
                        ):
                            childfullname = fullname + "." + item[:-4]
                            stubs[childfullname] = StubFoundResult(
                                childfullname, itementry.path, False
                            )
                            seen_stubs.add(modname)
                        continue
                    # modname validation and check
                    modname = getmodulename(item)
                    if (
                        not modname
                        or modname in _special_exclude_modulename
                        or modname in seen
                    ):
                        continue
                    found_mod = (modname, False)
                if found_mod is None:
                    continue
                modname, is_package = found_mod
                childfullname = fullname + "." + modname
                if self.is_exclude_module(childfullname):
                    continue
                module = import_module(childfullname)
                modules[childfullname] = module
                seen.add(modname)
                if is_package:
                    self.scan_modules(childfullname, module.__path__, ctx)
        # search portions in namespace_path
        for item, path in namespace_path.items():
            if item in seen:
                continue
            if path:
                self.scan_modules(fullname + "." + item, path, ctx)
        return ctx

    def find_iter(
        self, module: t.Union[str, types.ModuleType]
    ) -> t.Iterator[_ModuleBoundResult]:
        if isinstance(module, str):
            module = import_module(module)
        # top-level needs a special treat because we don't want to
        # search in parent path or sys path
        create_mps = ModuleProperties.from_module
        file = module.__file__
        if file is None:
            yield (module.__name__, create_mps(module), None)
            return
        file_dir, basename = os.path.split(file)
        stub_path = os.path.join(file_dir, basename.split(".", 1)[0] + ".pyi")
        module_stub = None
        if os.path.isfile(stub_path):
            # top module has stub
            module_stub = create_module_from_sourcefile(
                module.__name__,
                module.__name__,
                is_package=hasattr(module, "__path__"),
            )
        yield (  # type: ignore  # mypy blames and operator
            module.__name__,
            create_mps(module),
            module_stub and create_mps(module_stub),
        )
        path = getattr(module, "__path__", None)
        if path is None:
            return
        modules, stubs = self.scan_modules(module.__name__, path, ({}, {}))
        modules = _fix_inconsistent_modules(modules)
        for name in sorted(modules.keys() | stubs.keys()):
            # here stubs maybe inconsistent namespace but we don't announce
            # user should check this
            submodule, stubresult = modules.get(name), stubs.get(name)
            # depart this line because pylance blame on NamedTuple
            submodule_stub = None
            if stubresult:
                submodule_stub = create_module_from_stub_result(stubresult)
            yield (  # type: ignore  # mypy
                name,
                submodule and create_mps(submodule),
                submodule_stub and create_mps(submodule_stub),
            )


def create_module_from_stub_result(res: StubFoundResult) -> types.ModuleType:
    return create_module_from_sourcefile(
        res.name, res.origin, is_package=res.is_package
    )


def create_module_from_sourcefile(
    fullname: str, path: str, *, is_package: t.Optional[bool] = None
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


def _fix_inconsistent_modules(
    modules: t.Dict[str, types.ModuleType]
) -> t.Dict[str, types.ModuleType]:
    """Order modules and fix intermediate missing module.

    Missing value is possibly namespace which skipped by `ModuleFinder.scan_modules`.
    """
    if len(modules) <= 1:
        return modules
    modules_unpack = sorted(modules.items())
    for index in range(len(modules_unpack) - 2, -1, -1):
        # implicit copy and reversed because size changes
        (name, _), (nextname, _) = modules_unpack[index : index + 2]
        if nextname.startswith(name + "."):
            rightname = nextname[len(name) + 1 :]
            if "." in rightname:
                modules_unpack[index + 1 : index + 1] = [
                    (modulename, import_module(modulename))
                    for modulename in islice(
                        accumulate(
                            ["." + i for i in rightname.split(".")][:-1],
                            initial=name,
                        ),
                        1,
                        None,
                    )
                ]
    return dict(modules_unpack)
