"""Inspect and analyze module from runtime and AST.

context 储存真实对象，不储存 ref。
module.members 储存可文档对象，包括 ref。

Module 处理标准:
    1. 所有子模块都会在内部 import（即使识别为黑名单），严格依照 __dict__ 顺序输出对象
    2. 任何 class, method, function 的 `__name__` 和 `__qualname__` 必须等于他们在模块中的名称

    考虑这样一个情况:
    ./
    main.py
    internal/
        __init__.py
    external/
        __init__.py
    internal 有个 Foo 类，包括成员 a 和 b，需要在 external 控制 Foo 和其成员要怎么做？
    * external 写 __autodoc__ 违反了原则: 只能允许控制子模块和当前模块
    * internal 写 __autodoc__ 造成文档和模块不一致，属于 implicit problem
    * 希望 __autodoc__ 和静态代码分析无关
    解决方案:
        对 __autodoc__ 限制类型: class, method, function 直接 introspect object
        "A.a" 则解析 A 得到 internal.A，将 internal.A.a 加入黑白名单（转交给 class 处理）

Module 处理流程:
    1. AST parse
        * 获取 variable comments，逻辑为 Assign 有 docstring 就 pick comment

Literal annotation:
    1. 验证是否 new style，由于 new style 处理过于复杂（FunctionType 嵌套和转换问题），对其只进行 refname 替换
    2. 不是 new style 则进行 evaluate

问题:
    1. 来自其他模块的对象在本模块输出，链接问题

"""
import types
from collections import UserDict
from importlib import import_module
from pkgutil import iter_modules
from typing import Any, Dict, List, Optional, Set, TypeVar, Union

from nb_autodoc.analyzer import Analyzer, convert_annot
from nb_autodoc.typing import T_Annot, T_ClassMember, T_ModuleMember, Tp_GenericAlias
from nb_autodoc.utils import (
    cached_property,
    cleandoc,
    eval_annot_as_possible,
    formatannotation,
    logger,
)

T = TypeVar("T")
TT = TypeVar("TT")
TD = TypeVar("TD", bound="Doc")


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


class ModuleManager:
    """Manager for module and submodules.

    To control module's documentable object, setting `__autodoc__` respected to:
        * module-level dict variable
        * target object must be class, method or function
        * key is the target object's qualified name in current module
        * value bool: True for whitelist, False for blacklist
        * value str: override target object's docstring

    Args:
        module: module name
        skip_modules: the module names to skip documentation
    """

    def __init__(
        self,
        module: Union[str, types.ModuleType],
        *,
        skip_modules: Optional[Set[str]] = None,
    ) -> None:
        self.context: Context[Doc] = Context()
        self.module = Module(module, skip_modules=skip_modules, _context=self.context)
        self.name = self.module.name
        self.modules = {module.name: module for module in self.module.list_modules()}
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
            if module.name != objbody.__module__:
                logger.info(
                    f"{module.name} | __autodoc__[{key!r}] reference to "
                    f"external {refname!r}"
                )
                module._externals[key] = External(refname)
            if value is True:
                module.context.whitelist.add(refname)
            elif value is False:
                module.context.blacklist.add(refname)
            elif isinstance(value, str):
                module.context.override_docstring[refname] = value
            else:
                logger.error(
                    f"{module.name}.__autodoc__[{key!r}] "
                    f"expects value bool or str, got {type(value)}"
                )


class Doc:
    docstring: Optional[str]


_modules: Dict[str, "Module"] = {}


class Module(Doc):
    """Analyze module."""

    # Slots that not setting instantly
    members: Dict[str, T_ModuleMember]
    _externals: Dict[str, "External"]
    _library_attrs: Dict[str, "LibraryAttr"]

    def __init__(
        self,
        module: Union[str, types.ModuleType],
        *,
        skip_modules: Optional[Set[str]] = None,
        _package: Optional["Module"] = None,
        _context: Optional[Context[Doc]] = None,
    ) -> None:
        """Find submodules and link."""
        if isinstance(module, str):
            module = import_module(module)
        self.obj = module
        self.docstring = module.__doc__ and cleandoc(module.__doc__)
        self.package = _package
        if _context is None:
            raise TypeError("Module cannot be instantiated, use ModuleManager instead")
        self.context = _context
        _modules[self.name] = self

        if skip_modules is not None:
            self.context.skip_modules |= skip_modules

        # Find submodules
        self.submodules: Optional[Dict[str, Module]] = None
        if self.is_package:
            self.submodules = {}
            for finder, name, ispkg in iter_modules(self.obj.__path__):
                self.submodules[name] = Module(
                    f"{self.name}.{name}", _package=self, _context=self.context
                )

    def __repr__(self) -> str:
        return f"<{'Package' if self.is_package else 'Module'} {self.name!r}>"

    def _evaluate(self, s: str) -> Any:
        return eval(s, self._analyzer.globalns)

    @property
    def __autodoc__(self) -> Dict[str, Union[bool, str]]:
        return getattr(self.obj, "__autodoc__", {})

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
            globalns=self.obj.__dict__.copy(),
        )
        for name, obj in self.obj.__dict__.items():
            if name in self._analyzer.var_comments:
                ...
                continue
            module = getattr(obj, "__module__", None)
            if module is None:
                self.members
            elif module == self.name:
                ...
            else:
                # Possibly cause by overrided __getattr__ or builtins instance
                self.members


class Class(Doc):
    """Analyze class."""

    def __init__(self, name: str, obj: type, module: Module) -> None:
        self.name = name
        self.docstring = obj.__doc__ and cleandoc(obj.__doc__)
        self.obj = obj
        self.module = module
        # validate class.__name__ and __qualname__ if equals to name (for annot eval)

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

    # if no __doc__, found from __func__ exists
    # search source from linecache


NULL = object()


class Variable(Doc):
    """Analyze variable."""

    def __init__(
        self,
        name: str,
        module: Module,
        annot: T_Annot = NULL,
        *,
        cls: Optional[Class] = None,
    ) -> None:
        self.name = name
        self.module = module
        self.cls = cls
        self._annot = annot

    @cached_property
    def annotation(self) -> str:
        annot = self._annot
        if annot is NULL or annot is ...:
            return "untyped"
        elif isinstance(annot, str):
            if "->" in annot:
                logger.warning(f"disallow alternative Callable syntax in {annot!r}")
                return self.replace_annot_refs(annot)
            # TODO: add "X | Y" parser feature
            try:
                annot = self.module._evaluate(annot)
            except Exception as e:  # TypeError if "X | Y"
                logger.error(f"evaluating annotation from {self.refname}: {e}")
            else:
                annot = formatannotation(annot)
        elif isinstance(annot, Tp_GenericAlias):
            annot = eval_annot_as_possible(
                annot,
                self.module.globalns,
                f"failed evaluating annotation {self.refname}",
            )
            annot = formatannotation(annot)
        else:  # type or None
            annot = formatannotation(annot)
        return convert_annot(self.replace_annot_refs(annot))

    def replace_annot_refs(self, s: str) -> str:
        return s

    @property
    def qualname(self) -> str:
        if self.cls is None:
            return self.name
        return f"{self.cls.name}.{self.name}"

    @property
    def refname(self) -> str:
        return f"{self.module.name}.{self.qualname}"


class Property(Variable):
    """Analyze property."""


class External(Doc):
    """Placeholder for external."""

    def __init__(self, refname: str) -> None:
        self.refname = refname


class LibraryAttr(Doc):
    """Storage for user library attribute."""

    def __init__(self, docname: str, doc: str) -> None:
        self.docname = docname
        self.docstring = cleandoc(doc)
