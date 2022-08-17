"""Import, inspect and link both runtime module and source code.

context 储存真实对象，不储存 ref。
module.members 储存可文档对象，包括 ref。

Module 处理标准:
    1. 所有子模块都会在内部 import（即使识别为黑名单），严格依照 __dict__ 顺序输出对象
    2. 三种 annotation 形式: type, string, typing.xxx object
    3. type alias 识别: variable 为 type 或者拥有 __origin__, __args__, __parameters__ 三个属性，
        为什么不识别模块名 typing ?: 可以同时处理 types.GenericAlias
    4. 任何 class, method, function 的 `__name__` 和 `__qualname__` 必须等于他们在模块中的名称

黑白名单和 Ref 处理:
    1. 为了避免子模块和包变量重名问题，默认输出所有模块，在构造时给予 skip_modules 变量，
        下划线开头模块会自动加入这个变量

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
        对 __autodoc__ 限制类型: class, method, function，额外增加 ref 黑白名单
        在原来的基础上，从 obj 获取 __module__，直接 resolve 成 refname，加入 ref 黑白名单

    annotation ref: refname to docname (url)
    doc ref: docname to refname (find definition)

Module 处理流程:
    1. AST parse
        1. 获取 variable comments，逻辑为 Assign 有 docstring 就 pick comment，
            名称非 _ 开头即为 public，所有 FunctionDef 和 ClassDef 的 qualname
    2. 模块对象过滤并实例化文档对象，copy __dict__ 并构建各自的 globalns，黑名单暂时不处理，
        如果为白名单则创建为 ForwardRef（为了保持顺序）。
    3. 构建 Document Tree。

Literal annotation:
    1. 验证是否 new style，由于 new style 处理过于复杂（FunctionType 嵌套和转换问题），对其只进行 refname 替换
    2. 不是 new style 则进行 evaluate

问题:
    1. 来自其他模块的对象在本模块输出，链接问题

"""
import sys
import types
from collections import UserDict
from importlib import import_module
from operator import attrgetter
from pkgutil import iter_modules
from typing import Any, Dict, Generic, Optional, Set, Type, TypeVar, Union

from nb_autodoc.analyzer import Analyzer, convert_annot
from nb_autodoc.typing import T_Annot, T_ClassMember, T_ModuleMember, Tp_GenericAlias
from nb_autodoc.utils import (
    cached_property,
    eval_annot_as_possible,
    formatannotation,
    logger,
)

T = TypeVar("T")
TT = TypeVar("TT")
TD = TypeVar("TD", bound="Doc")


_modules: Dict[str, "Module"] = {}


class Context(UserDict[str, TD]):
    """Store definition, equals to all module's members.

    * Avoid same name on submodule and variable
    """

    def __init__(self) -> None:
        super().__init__()
        # Store object refname retrieve from __autodoc__
        self.whitelist: Set[str] = set()
        self.blacklist: Set[str] = set()
        self.override_docstring: Dict[str, str] = {}
        self.skip_modules: Set[str] = set()


class DocMixin:
    """Common documentation attributes."""

    __dmodule__: str
    __dtype__: str


class Doc(DocMixin):
    docstring: Optional[str]


class Identity(Doc):
    """Placeholder for external."""

    def __init__(self, refname: str) -> None:
        self.refname = refname


class Module(Doc):
    """Import and analyze module and submodules.

    To control module's documentable object, setting `__autodoc__` respected to:
        * module-level dict variable
        * target object SHOULD be class, method or function
        * key is the target object's qualified name
        * value bool: True for whitelist, False for blacklist
        * value str: override target object's docstring
        * skip if setting in skip_modules

    Args:
        module: module name
        skip_modules: the full module names to skip documentation
    """

    members: Dict[str, T_ModuleMember]

    def __init__(
        self,
        module: Union[str, types.ModuleType],
        *,
        skip_modules: Optional[Set[str]] = None,
        _package: Optional["Module"] = None,
        _context: Optional[Context[Doc]] = None,
    ) -> None:
        """Find submodules and retrieve white and black list."""
        if isinstance(module, str):
            module = import_module(module)
        self.obj = module
        self.docstring = module.__doc__
        self.package = _package
        if _context is None:
            _context = Context()
        self.context = _context
        _modules[self.name] = self

        # Resolve __autodoc__
        # Target object always imported (how about LazyImport?)
        self._external: Dict[str, Identity] = {}
        for qualname, value in self.__autodoc__.items():
            try:
                obj = attrgetter(qualname)(self.obj)
            except AttributeError:
                logger.error(
                    f"{self.name}.__autodoc__: attribute {qualname!r} is "
                    "not found in globals, skip"
                )
                continue
            try:
                obj_modulename = getattr(obj, "__module__")
                obj_qualname = getattr(obj, "__qualname__")
            except AttributeError:
                # Could not interinspect the variable module
                # TODO: analyze definition and filter import stmt to find out module
                logger.warning(
                    f"{self.name}.__autodoc__: attribute {qualname!r} is "
                    f"expected to be class, method and function, "
                    f"got {type(obj)}, skip. "
                    "Re-export a variable is currently not supported. "
                    "Setting variable docstring if you want to force-export it."
                )
                continue
            # Do some necessary runtime check
            obj_module = sys.modules[obj_modulename]
            try:
                if attrgetter(obj_qualname)(obj_module) is not obj:
                    raise AttributeError
            except AttributeError:
                logger.error(
                    f"{obj_modulename}.{obj_qualname} has inconsistant "
                    "qualified name in runtime during __autodoc__ resolving, skip"
                )
                continue
            # Storage from qualname, obj_module, obj_qualname
            obj_refname = f"{obj_modulename}.{obj_qualname}"
            if self.name != obj_modulename:
                self._external[qualname] = Identity(obj_refname)
            if value is True:
                self.context.whitelist.add(obj_refname)
            elif value is False:
                self.context.blacklist.add(obj_refname)
            elif isinstance(value, str):
                self.context.override_docstring[obj_refname] = value
            else:
                logger.warning(
                    f"{self.name}.__autodoc__: "
                    f"expects value to be bool or str, got {type(value)}"
                )

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
        return eval(s, self.globalns)

    @property
    def __autodoc__(self) -> Dict[str, Union[bool, str]]:
        return getattr(self.obj, "__autodoc__", {})

    @property
    def name(self) -> str:
        return self.obj.__name__

    @property
    def filepath(self) -> str:
        # No check for <string> or <unknown> or None
        return self.obj.__file__  # type: ignore

    @property
    def globalns(self) -> Dict[str, Any]:
        return self._analyzer.globalns

    @property
    def is_package(self) -> bool:
        return hasattr(self.obj, "__path__")

    def analyze(self) -> None:
        """Traverse all submodules and specify the object from runtime and AST.

        Call this method after instance initialization. `__autodoc__` should be
        resolved completely before calling.

        This method creates the definition namespace. For those external
        """
        self.members = {}
        self._analyzer = Analyzer(
            self.name,
            self.package.name if self.package is not None else None,
            self.filepath,
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

    def spec_and_create(self, obj: Any) -> T_ModuleMember:
        ...


class Class(Doc):
    def __init__(self, name: str, obj: type, module: Module) -> None:
        self.name = name
        self.docstring = obj.__doc__
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
    SPECIAL_MEMBERS = ["__get__", "__set__", "__delete__"]


class Enum(Class):
    ...


class Function(Doc):
    ...
    # if no __doc__, found from __func__ exists
    # search source from linecache


NULL = object()


class Variable(Doc):
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
    ...
