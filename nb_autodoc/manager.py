"""Inspect and analyze module from runtime and AST."""

import types
from collections import ChainMap
from contextvars import ContextVar
from typing import Any, Dict, NamedTuple, Optional, Set, TypeVar, Union, cast

from nb_autodoc.analyzers.analyzer import Analyzer
from nb_autodoc.analyzers.definitionfinder import ImportFromData
from nb_autodoc.config import Config, default_config
from nb_autodoc.log import logger
from nb_autodoc.modulefinder import ModuleFinder, ModuleProperties
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

T_Definition = Union["Class", "Function", "Variable"]
T_Autodoc = Dict[str, Union[bool, str]]


current_module: ContextVar["Module"] = ContextVar("current_module")
# NOTE: isfunction not recognize the C extension function (builtin), maybe isroutine and callable


class AutodocRefineResult(NamedTuple):
    module: str
    attr: str
    is_ref: bool
    is_library: bool


def _refine_autodoc_from_ast(
    module: "Module", name: str
) -> Optional[AutodocRefineResult]:
    """Return source module where has name definition."""
    # should be circular guarded?
    chain = []
    attrs = []
    while True:
        analyzer = module.pyi_analyzer or module.py_analyzer
        assert analyzer, "found '__autodoc__' on non-source file"
        ast_obj = analyzer.scope.get(name)
        if ast_obj is None:
            return None
        if isinstance(ast_obj, ImportFromData):
            # found reference or library
            modules = module.manager.modules
            if ast_obj.module in modules:
                chain.append(module.name)
                attrs.append(name)
                module = modules[ast_obj.module]
                name = ast_obj.orig_name  # original name
            else:
                # if chain:  # ref should not be library
                #     return AutodocRefineResult(module.name, name, True, True)
                return AutodocRefineResult(module.name, name, False, True)
        else:
            # found definition
            if chain:
                return AutodocRefineResult(module.name, name, True, False)
            return AutodocRefineResult(module.name, name, False, False)


class ModuleManager:
    """Manager shares the state for module and submodules.

    To control module's documentable object, setting `__autodoc__` respects to:
        * module-level dict variable
        * key is the target object's qualified name in current module
        * value bool: True for whitelist, False for blacklist
        * value str: override target object's docstring

    Args:
        module: module or package
    """

    def __init__(
        self,
        module: Union[str, types.ModuleType],
        *,
        config: Config = default_config,
    ) -> None:
        self.context: ChainMap[str, Any] = ChainMap()
        self.config: Config = config
        self.name = module if isinstance(module, str) else module.__name__
        module_found_result = ModuleFinder(config).find_all_modules_wrapped(module)
        self.modules: Dict[str, Module] = {
            name: Module(self, name, py=m, pyi=ms)
            for name, m, ms in module_found_result.gen_bound_module()
        }
        self.whitelist: Set[str] = set()
        """Whitelist fullname refined from `__autodoc__`."""
        self.blacklist: Set[str] = set()
        """Blacklist fullname refined from `__autodoc__`."""
        # generate whitelist / blacklist, module reference / libraryattr
        # refine autodoc before prepare
        self.refine_autodoc(self.modules)
        # for dmodule in self.modules.values():
        #     dmodule.prepare()

    def refine_autodoc(self, modules: Dict[str, "Module"]) -> None:
        # clear manager context
        self.whitelist.clear()
        self.blacklist.clear()
        for module in modules.values():
            # clear module context
            module.exist_reference.clear()
            module.exist_libraryattr.clear()
            autodoc = module.get__autodoc__(sort=False)
            for key, value in autodoc.items():
                name, _, attr = key.partition(".")
                result = _refine_autodoc_from_ast(module, name)
                if result is None:
                    logger.error(f"__autodoc__[{key!r}] not found")
                    continue
                if result.is_ref:
                    module.exist_reference[name] = Reference(
                        self, result.module, result.attr
                    )
                elif result.is_library:
                    if result.module != module.name:
                        logger.error(
                            f"__autodoc__[{key!r}] is external import "
                            "but ends as library attribute"
                        )
                        continue
                    if attr:
                        logger.error(
                            f"__autodoc__[{key!r}] is library attribute "
                            f"with ambitious attr {attr!r}"
                        )
                        continue
                    if not isinstance(value, str):
                        logger.error(
                            f"__autodoc__[{key!r}] is library attribute "
                            f"and expects string value to override, got {type(value)}"
                        )
                        continue
                    module.exist_libraryattr[name] = LibraryAttr(name, value)
                refname = result.module + "." + result.attr
                if attr:  # no check attr existence
                    refname += "." + attr
                if value is True or isinstance(value, str):
                    self.whitelist.add(refname)
                elif value is False:
                    self.blacklist.add(refname)
                else:
                    logger.error(f"__autodoc__[{key!r}] got unexpected value {value}")

    def push_context(self, d: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Push context. Like inplace `ChainMap.new_child`."""
        if d is None:
            d = {}
        self.context.maps.insert(0, d)
        return d

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name!r}>"


# external has two type "Reference" and "LibraryAttr"
class Reference:
    """External reference."""

    __slots__ = ("manager", "module", "attr")

    def __init__(self, manager: ModuleManager, module: str, attr: str) -> None:
        self.manager = manager
        self.module = module
        self.attr = attr

    def get(self) -> Optional[T_ModuleMember]:
        module = self.manager.modules.get(self.module)
        if module is None:
            return None
        return module.members.get(self.attr)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(manager={self.manager!r}, "
            f"module={self.module!r}, attr={self.attr!r})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Reference):
            return False
        return (
            self.manager is other.manager
            and self.module == other.module
            and self.attr == other.attr
        )


class LibraryAttr:
    """External library attribute."""

    __slots__ = ("name", "docstring")

    def __init__(self, name: str, doc: str) -> None:
        self.name: str = name
        self.docstring: str = cleandoc(doc)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name={self.name!r}, "
            f"docstring={self.docstring!r})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LibraryAttr):
            return False
        return self.name == other.name and self.docstring == other.docstring


class Module:
    """Analyze module."""

    def __init__(
        self,
        manager: "ModuleManager",
        name: str,
        *,
        py: Optional[ModuleProperties] = None,
        pyi: Optional[ModuleProperties] = None,
    ) -> None:
        self.manager = manager
        self.members = manager.push_context()
        self.name = name
        # if py and pyi both exist, then py (include extension) is only used to extract docstring
        # if one of them exists, then analyze that one
        # if py is not sourcefile, pyi must be specified (find definition), otherwise skip
        # such as numpy._typing._ufunc or torch._C._autograd
        if py is None and pyi is None:
            raise RuntimeError
        self.py = py
        self.pyi = pyi
        self.prepared = False
        py_analyzer = pyi_analyzer = None
        if py and py.is_source:
            py_analyzer = Analyzer(self.name, self.package, cast(str, py.sm_file))
        if pyi:  # pyi always sourcefile
            pyi_analyzer = Analyzer(self.name, self.package, cast(str, pyi.sm_file))
        self.py_analyzer = py_analyzer
        self.pyi_analyzer = pyi_analyzer

        self.exist_reference: Dict[str, Reference] = {}
        self.exist_libraryattr: Dict[str, LibraryAttr] = {}

    @property
    def is_pure_c_extension(self) -> bool:
        if self.pyi is None and self.py is not None:
            return self.py.is_c_module
        return False

    @property
    def package(self) -> Optional[str]:
        if self.py:
            return self.py.sm_package
        if self.pyi:
            return self.pyi.sm_package
        raise RuntimeError

    def get__autodoc__(self, sort: bool = True) -> T_Autodoc:
        """Retrieve `__autodoc__` bound on current module."""
        res: T_Autodoc = {}
        if self.py:
            res.update(self.py.sm_dict.get("__autodoc__", ()))
        if self.pyi:
            res.update(self.pyi.sm_dict.get("__autodoc__", ()))
        assert all(
            all(name.isidentifier() for name in qualname.split(".")) for qualname in res
        ), f"bad '__autodoc__': {res}"
        if sort:
            return {k: res[k] for k in sorted(res)}
        return res

    def _evaluate(self, s: str) -> Any:
        # numpy._typing has stmt like `if TYPE_CHECKING...else...`
        # so we need to directly update copied globalns rather than ChainMap
        return eval(s, self.obj.__dict__)

    def is_include(self, name: str) -> bool:
        return self.name + "." + name in self.manager.whitelist

    def is_exclude(self, name: str) -> bool:
        if name.startswith("_") or self.name + "." + name in self.manager.blacklist:
            return True
        return False

    def prepare(self) -> None:
        """Build module members.

        Create definition namespace, create placeholder for external.
        Ensure `__autodoc__` has been resolved before calling this method.
        """
        if not hasattr(self, "_externals") or not hasattr(self, "_library_attrs"):
            raise ValueError(f"unable to prepare {self.name}")
        if self.prepared or self.is_pure_c_extension:
            return
        self.members.clear()
        py = self.py
        pyi = self.pyi

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

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} {self.name!r} "
            f"py from {self.py and self.py.sm_file!r} "
            f"pyi from {self.pyi and self.pyi.sm_file!r}>"
        )


class Class:
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
        # solve ClassVar declaration

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


# TODO: add MethodType support on module-level, those are alias of bound method
class Function:
    """Analyze function.

    **Overloads:**

    In py3.11+, `typing.get_overloads` is implemented based on overload registry dict
    like `{module: {qualname: {firstlineno: func}}}`, so stub evaluation will cover
    the potential overloads. We do not take care of this implementation.
    """

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
        # evaluate signature_from_ast `expr | str` using globals and class locals
        # __text_signature__ should be respected
        # https://github.com/python/cpython/blob/5cf317ade1e1b26ee02621ed84d29a73181631dc/Objects/typeobject.c#L8597

    @property
    def docstring(self) -> Optional[str]:
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


class Variable:
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


class DynamicClassFunction:
    """Analyze dynamic class or function."""

    def __init__(self, name: str, obj: Any, module: Module) -> None:
        self.name = name
        self.obj = obj
        self.module = module

    @property
    def comment(self) -> str:
        return self.module._analyzer.var_comments[self.name]
