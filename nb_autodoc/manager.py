"""Inspect and analyze module from runtime and AST."""

import types
from collections import ChainMap, UserDict
from contextvars import ContextVar
from typing import Any, Dict, List, Optional, Set, TypeVar, Union

# from nb_autodoc.analyzer import Analyzer, convert_annot
from nb_autodoc.config import Config, default_config
from nb_autodoc.log import logger
from nb_autodoc.modulefinder import ModuleFinder, ModuleProperties
from nb_autodoc.nodes import Page
from nb_autodoc.typing import T_Annot, T_ClassMember, T_ModuleMember, Tp_GenericAlias
from nb_autodoc.utils import (
    cached_property,
    cleandoc,
    eval_annot_as_possible,
    formatannotation,
    safe_getattr,
)

T = TypeVar("T")
TT = TypeVar("TT")
TD = TypeVar("TD", bound="Doc")


modules: Dict[str, "Module"] = {}
current_module: ContextVar["Module"] = ContextVar("current_module")
# maybe useful in builder
# NOTE: isfunction not recognize the C extension function (builtin), maybe isroutine and callable


class Context(UserDict[str, TD]):
    """Store definitions.

    Equals to all members except Module, External and LibraryAttr.
    """

    def __init__(self) -> None:
        super().__init__()
        # Store object refname retrieve from __autodoc__
        self.whitelist: Set[str] = set()
        self.blacklist: Set[str] = set()
        self.override_docstring: Dict[str, str] = {}
        self.skip_modules: Set[str] = set()


# Source Module Manager 和 Extension Module Manager
# 主要区别在于 build_node 方法，保证每个模块 build 一个 page，key 为模块名
class ModuleManager:
    """Manager shares the state for module and submodules.

    To control module's documentable object, setting `__autodoc__` respects to:
        * module-level dict variable
        * key is the target object's qualified name in current module
        * value bool: True for whitelist, False for blacklist
        * value str: override target object's docstring

    `iter_modules` is used to find submodule of the pass-in module (Path entry finder).
    `import_module` is used to import submodules. Namespace package is disallowed.

    Args:
        module: module name
        skip_modules: the module names to skip documentation
    """

    def __init__(
        self, module: Union[str, types.ModuleType], *, config: Config = default_config
    ) -> None:
        self.ctx: Context[Doc] = Context()
        # TODO: use ChainMap
        self.nodes: Dict[str, Page]
        """data bus for all module analyzer to add node."""
        self.module = Module(self)
        self.name = self.module.name
        self.config = config.copy()
        self.modules = {module.name: module for module in self.module.list_modules()}
        modules.update(self.modules)

        for dmodule in self.modules.values():
            self.resolve_autodoc(dmodule)
        for dmodule in self.modules.values():
            dmodule.prepare()

    def resolve_autodoc(self, module: "Module") -> None:
        module._externals = {}
        module._library_attrs = {}
        for key, value in module.__autodoc__.items():
            name, _, attr = key.partition(".")
            # Leave attr (if exists) to its class to resolve
            try:
                objbody = module.obj.__dict__[name]
            except KeyError:
                logger.error(
                    f"{module.name} | __autodoc__[{key!r}] is "
                    "not found in globals, skip"
                )
                continue
            if not isinstance(objbody, (type, types.FunctionType, types.MethodType)):
                # Could not introspect builtins data or instance
                # TODO: analyze import stmt to find out module
                logger.error(
                    f"{module.name} | __autodoc__[{key!r}] {name!r} is "
                    f"expected to be class, method or function, "
                    f"got {type(objbody)!r}, skip. "
                    "Re-export a variable is currently not supported. "
                    "Setting docstring to variable if you want to force-export it."
                )
                continue
            # intrespect is unreliable (e.g. dynamic class or function)
            if "<locals>" in objbody.__qualname__:
                continue
            refname = f"{objbody.__module__}.{objbody.__qualname__}"
            if attr:
                refname += "." + attr
            # User library
            if objbody.__module__ not in self.modules:
                logger.info(
                    f"{module.name} | __autodoc__[{key!r}] reference to "
                    f"user library {refname!r}"
                )
                if not isinstance(value, str):
                    raise ValueError(
                        f"{module.name}.__autodoc__[{key!r}] is a user library "
                        f"and expects docstring, got value {type(value)}"
                    )
                # Key must be identifier
                module._library_attrs[key] = LibraryAttr(key, value)
                continue
            # External
            if module.name != objbody.__module__ and not attr:
                logger.info(
                    f"{module.name} | __autodoc__[{key!r}] reference to "
                    f"external {refname!r}"
                )
                module._externals[key] = External(refname)
            if value is True:
                module.manager.ctx.whitelist.add(refname)
            elif value is False:
                module.manager.ctx.blacklist.add(refname)
            elif isinstance(value, str):
                module.manager.ctx.override_docstring[refname] = value
            else:
                logger.error(
                    f"{module.name}.__autodoc__[{key!r}] "
                    f"expects value bool or str, got {type(value)}"
                )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name!r}>"


class Doc:
    docstring: Optional[str]


class Module(Doc):
    """Analyze module."""

    # Slots that not setting instantly
    members: Dict[str, T_ModuleMember]
    _externals: Dict[str, "External"]
    _library_attrs: Dict[str, "LibraryAttr"]
    _dynamic_class_or_function: Set[str]

    def __init__(
        self,
        manager: "ModuleManager",
        *,
        py: Optional[ModuleProperties] = None,
        pyi: Optional[ModuleProperties] = None,
    ) -> None:
        # source file is optional for those dynamic module has no origin
        # such as numpy._typing._ufunc or torch._C._autograd
        # TODO: numpy._typing has stmt like `if TYPE_CHECKING...else...`
        # so we need to directly update copied globalns rather than ChainMap
        self.manager = manager
        self.py = py
        self.pyi = pyi

    def __repr__(self) -> str:
        return f"<{'Package' if self.is_package else 'Module'} {self.name!r}>"

    def _evaluate(self, s: str) -> Any:
        # TODO: use ChainMap namespace order: __dict__ > TYPE_CHECKING
        return eval(s, self.obj.__dict__)

    @property
    def __autodoc__(self) -> Dict[str, Union[bool, str]]:
        return getattr(self.obj, "__autodoc__", {})

    @property
    def annotations(self) -> Dict[str, T_Annot]:
        return getattr(self.obj, "__annotations__", {})

    @property
    def name(self) -> str:
        return self.obj.__name__

    @property
    def file(self) -> str:
        # No check for <string> or <unknown> or None
        return self.obj.__file__  # type: ignore

    @property
    def is_package(self) -> bool:
        return hasattr(self.obj, "__path__")

    @property
    def prepared(self) -> bool:
        return hasattr(self, "members")

    @classmethod
    def create(cls) -> "Module":
        obj = super().__new__(cls)

    def list_modules(self) -> List["Module"]:
        res: List[Module] = [self]
        if self.submodules is None:
            return res
        for module in self.submodules.values():
            if module.is_package:
                res.extend(module.list_modules())
            else:
                res.append(module)
        return res

    def prepare(self) -> None:
        """Construct the module members.

        Create definition namespace, create placeholder for external.
        Ensure `__autodoc__` has been resolved before calling this method.
        """
        if not hasattr(self, "_externals") or not hasattr(self, "_library_attrs"):
            raise ValueError(f"unable to prepare {self.name}")
        if self.prepared:
            return
        self.members = {}
        package = self.package.name if self.package is not None else None
        if package is None and "." in self.name:
            # Self is top module and submodule of unknown package
            if self.is_package:
                package = self.name
            else:
                package = self.name.rsplit(".", 1)[0]
        self._analyzer = Analyzer(
            self.name,
            package,
            self.file,
        )
        self._analyzer.analyze()
        for name, obj in self.obj.__dict__.items():
            if name in self._externals:
                self.members[name] = self._externals.pop(name)
                continue
            if name in self._library_attrs:
                self.members[name] = self._library_attrs.pop(name)
                continue
            if "<locals>" in getattr(obj, "__qualname__", ""):
                if name in self._analyzer.var_comments:
                    self.members[name] = DynamicClassFunction(name, obj, self)
                continue
            # None if getattr overrided or builtins instance
            module = getattr(obj, "__module__", None)
            if module == self.name:
                refname = f"{module}.{name}"
                if refname in self.manager.ctx.blacklist:
                    continue
                if name.startswith("_") and refname not in self.manager.ctx.whitelist:
                    continue
                if isinstance(obj, type):
                    self.members[name] = Class(name, obj, self)
                elif isinstance(obj, (types.FunctionType, types.MethodType)):
                    self.members[name] = Function(name, obj, self)
                continue
            elif name in self._analyzer.var_comments:
                self.members[name] = Variable(name, self)
        else:
            if self._externals:
                logger.warning(f"{self.name} | unused _externals {self._externals}")
            if self._library_attrs:
                logger.warning(
                    f"{self.name} | unused _library_attrs {self._library_attrs}"
                )


class Class(Doc):
    """Analyze class."""

    def __init__(self, name: str, obj: type, module: Module) -> None:
        self.name = name
        self.docstring = obj.__doc__ and cleandoc(obj.__doc__)
        self.obj = obj
        self.module = module
        self.inst_vars: Set[str] = set()
        if self.refname != f"{obj.__module__}.{obj.__qualname__}":
            logger.warning(
                f"{self.module.name} | {self.qualname!r} has inconsistant "
                f"runtime module {obj.__module__!r} or qualname {obj.__qualname__!r}. "
                "This is possibly caused by dynamic class creation."
            )

    @property
    def annotations(self) -> Dict[str, T_Annot]:
        return getattr(self.obj, "__annotations__", {})

    @property
    def qualname(self) -> str:
        return self.name  # Nested class not support

    @property
    def refname(self) -> str:
        return f"{self.module.name}.{self.name}"


class Descriptor(Class):
    """Analyze descriptor class."""

    SPECIAL_MEMBERS = ["__get__", "__set__", "__delete__"]


class Enum(Class):
    """Analyze enum class."""


class Function(Doc):
    """Analyze function."""

    def __init__(
        self,
        name: str,
        obj: Union[types.FunctionType, types.MethodType],
        module: Module,
        *,
        cls: Optional[Class] = None,
    ) -> None:
        self.name = name
        self.obj = obj
        self.module = module
        self.cls = cls
        if self.refname != f"{obj.__module__}.{obj.__qualname__}":
            logger.warning(
                f"{self.module.name} | {self.qualname!r} has inconsistant "
                f"runtime module {obj.__module__!r} or qualname {obj.__qualname__!r}. "
                "This is possibly caused by dynamic function creation."
            )

    @property
    def docstring(self) -> Optional[str]:  # type: ignore[override]
        doc = self.module._analyzer.var_comments.get(self.qualname, self.obj.__doc__)
        if doc is None and hasattr(self.obj, "__func__"):
            doc = getattr(self.obj, "__func__").__doc__
        return doc

    @property
    def qualname(self) -> str:
        if self.cls:
            return f"{self.cls.qualname}.{self.name}"
        return self.name

    @property
    def refname(self) -> str:
        return f"{self.module.name}.{self.qualname}"


NULL = object()


class Variable(Doc):
    """Analyze variable."""

    def __init__(
        self,
        name: str,
        module: Module,
        *,
        cls: Optional[Class] = None,
    ) -> None:
        self.name = name
        self.module = module
        self.cls = cls

    @cached_property
    def annot(self) -> T_Annot:
        if not self.cls:
            return self.module.annotations.get(self.name, NULL)
        elif self.name in self.cls.annotations:
            return self.cls.annotations[self.name]
        elif self.name in self.cls.inst_vars:
            return self.module._analyzer.annotations.get(self.refname, NULL)

    @cached_property
    def annotation(self) -> str:
        annot = self.annot
        if annot is NULL:
            return "untyped"
        elif isinstance(annot, str):
            if "->" in annot:
                logger.warning(
                    f"{self.module.name} | disallow alternative Callable syntax "
                    f"in {self.qualname} {annot!r}"
                )
                return self.replace_annot_refs(annot)
            # TODO: add "X | Y" parser feature
            try:
                annot = self.module._evaluate(annot)
            except Exception as e:  # TypeError if "X | Y"
                logger.error(
                    f"{self.module.name} | error evaluating annotation {self.qualname} {e}"
                )
            else:
                annot = formatannotation(annot, {})
        elif isinstance(annot, Tp_GenericAlias):
            annot = eval_annot_as_possible(
                annot,
                self.module.obj.__dict__,
                f"failed evaluating annotation {self.refname}",
            )
            annot = formatannotation(annot, {})
        else:  # type or None
            annot = formatannotation(annot, {})
        return convert_annot(self.replace_annot_refs(annot))

    @property
    def qualname(self) -> str:
        if self.cls is None:
            return self.name
        if self.name in self.cls.inst_vars:
            return f"{self.cls.qualname}.__init__.{self.name}"
        else:
            return f"{self.cls.qualname}.{self.name}"

    @property
    def refname(self) -> str:
        return f"{self.module.name}.{self.qualname}"

    @property
    def comment(self) -> str:
        """Variable always has comment."""
        return self.module._analyzer.var_comments[self.qualname]

    def replace_annot_refs(self, s: str) -> str:
        return s


class Property(Variable):
    """Analyze property."""


class DynamicClassFunction(Doc):
    """Analyze dynamic class or function."""

    def __init__(self, name: str, obj: Any, module: Module) -> None:
        self.name = name
        self.obj = obj
        self.module = module

    @property
    def comment(self) -> str:
        return self.module._analyzer.var_comments[self.name]


class External(Doc):
    """Placeholder for external."""

    def __init__(self, refname: str) -> None:
        self.refname = refname


class LibraryAttr(Doc):
    """Storage for user library attribute."""

    def __init__(self, docname: str, doc: str) -> None:
        self.docname: str = docname
        self.docstring: str = cleandoc(doc)
