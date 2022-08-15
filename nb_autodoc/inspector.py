"""Import, inspect and link both runtime module and source code.

context 储存真实对象，不储存 ref。
module.members 储存可文档对象，包括 ref。

Module 处理标准:
    1. 所有子模块都会在内部 import（即使识别为黑名单），严格依照 __dict__ 顺序输出对象
    2. 三种 annotation 形式: type, string, typing.xxx object
    3. type alias 识别: variable 为 type 或者拥有 __origin__, __args__, __parameters__ 三个属性，
        为什么不识别模块名 typing ?: 可以同时处理 types.GenericAlias

黑白名单和 Ref 处理:
    1. 为了避免子模块和包变量重名问题，默认输出所有模块，在构造时给予 skip_modules 变量，
        下划线开头模块会自动加入这个变量

    考虑这样一个情况，internal 子模块为黑名单，但是其中一个类需要在 foo 外部模块输出，我想控制类的成员怎么做？
    我不想在 internal 任何一个模块增加 __autodoc__，增加了复杂性，但是需要进行支持
    所有 Document Object 提供一个 dmodule 变量，为本模块输出文档位置。

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
import types
from collections import UserDict
from importlib import import_module
from pkgutil import iter_modules
from typing import (
    Any,
    Dict,
    Generic,
    Optional,
    Set,
    Type,
    TypeVar,
    Union,
    get_type_hints,
)

from nb_autodoc.analyzer import Analyzer
from nb_autodoc.typing import T_Annot, T_ClassMember, T_ModuleMember

T = TypeVar("T")
TD = TypeVar("TD", bound="Doc")


_modules: Dict[str, "Module"] = {}


def find_name_in_mro(cls: type, name: str, default: Any) -> Any:
    for base in cls.__mro__:
        if name in vars(base):
            return vars(base)[name]
    return default


class Context(UserDict[str, TD]):
    """Store definition, equals to all module's members.

    * Avoid same name on submodule and variable
    """

    def __init__(self) -> None:
        super().__init__()
        self.whitelist: Set[str] = set()
        self.blacklist: Set[str] = set()
        self.override_docstring: Dict[str, str] = {}
        self.skip_modules: Set[str] = set()


class ABCAttribute(Generic[T]):
    __slots__ = ("attr",)
    attr: T

    def __init__(self, _: Type[T]) -> None:
        super().__init__()

    def __get__(self, obj: Optional[type], objtype: Type[type]) -> T:
        if obj is None:
            return self  # type: ignore  # getattr from class
        if not hasattr(self, "attr"):
            raise NotImplementedError
        return self.attr

    def __set__(self, obj: type, value: T) -> None:
        self.attr = value


class DocMixin:
    """Common documentation attributes."""

    __dmodule__ = ABCAttribute(str)
    __dtype__ = ABCAttribute(str)


class Doc(DocMixin):
    docstring: Optional[str]


class Reexport(Doc):
    """Re-exported member for builder recognition."""


class Module(Doc):
    """Import and analyze module and submodules.

    To control module's documentable object, setting `__autodoc__` respected to:
        * module-level dict variable
        * module is documentable (skipped if setting in a skip_module)
        * key MUST be the current module's object's qualified name
            (even if it is force-exported to other modules)
        * value True for whitelist (force-exported), False for blacklist
        * value string will override target object's docstring

    Args:
        module: module name
        skip_modules: the full module names to skip documentation
    """

    __ddict__: Dict[str, Union[Reexport, T_ModuleMember]]
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

        for name, value in self.__autodoc__.items():
            refname = f"{self.name}.{name}"
            if value is True:
                self.context.whitelist.add(refname)
            elif value is False:
                self.context.blacklist.add(refname)
            elif isinstance(value, str):
                self.context.override_docstring[refname] = value

        if skip_modules is not None:
            self.context.skip_modules = skip_modules
        self.submodules: Optional[Dict[str, Module]] = None

        if self.is_package:
            self.submodules = {}
            for finder, name, ispkg in iter_modules(self.obj.__path__):
                self.submodules[name] = Module(
                    f"{self.name}.{name}", _package=self, _context=self.context
                )

        self.analyze()

    def __repr__(self) -> str:
        return f"<{'Package' if self.is_package else 'Module'} {self.name!r}>"

    @property
    def __autodoc__(self) -> Dict[str, Union[bool, str]]:
        return getattr(self.obj, "__autodoc__", {})

    @property
    def name(self) -> str:
        return self.obj.__name__

    @property
    def filepath(self) -> str:
        if self.obj.__file__ is None:
            raise RuntimeError
        return self.obj.__file__

    @property
    def is_package(self) -> bool:
        return hasattr(self.obj, "__path__")

    def analyze(self) -> None:
        """Traverse `__dict__` and specify the object from runtime and AST.

        Create definition namespace for documentation resolving.
        """
        self.members = {}
        self.analyzer = Analyzer(
            self.name,
            self.package.name if self.package is not None else None,
            self.filepath,
            globalns=self.obj.__dict__.copy(),
        )
        for name, obj in self.obj.__dict__.items():
            if hasattr(obj, "__module__"):
                obj.__module__

    def evaluate(self, expr: str) -> T_Annot:
        """Evaluate string literal type annotation."""
        return eval(expr, self.analyzer.globalns)


class Class(Doc):
    SPECIAL_MEMBERS = ["__get__", "__set__", "__delete__"]


class Descriptor(Class):
    ...


class Enum(Class):
    ...


class Function(Doc):
    ...


class Variable(Doc):
    ...


class Property(Variable):
    ...
