import __future__ as _future

import os
import sys
import typing as t
import typing_extensions as te
from importlib.machinery import all_suffixes
from types import BuiltinFunctionType, FunctionType, MappingProxyType
from typing import NamedTuple

_co_future_flags = {"annotations": _future.annotations.compiler_flag}
del _future

T = t.TypeVar("T")
TT = t.TypeVar("TT")
KT = t.TypeVar("KT")


_NULL: t.Any = object()


def safe_getattr(obj: t.Any, attr: str, default: t.Any = _NULL) -> t.Any:
    """Safe getattr that turns all exception into AttributeError."""
    if default is _NULL:
        try:
            return getattr(obj, attr)
        except Exception:
            raise AttributeError(f"{obj!r} has no attribute {attr!r}") from None
    else:
        try:
            return getattr(obj, attr, default)
        except Exception:
            return default


class TypeCheckingClass:
    """Dummy class for type checking.

    Usage: `type('_', (TypeCheckingClass,), {}, module='', qualname='')`
    """

    def __init__(self) -> None:
        raise TypeError(f"cannot instantiate {self}")

    @classmethod
    def create(cls, module: str, qualname: str) -> t.Type["TypeCheckingClass"]:
        return type("_", (cls,), {}, module=module, qualname=qualname)

    def __init_subclass__(cls, module: str, qualname: str) -> None:
        cls.__module__ = module
        cls.__qualname__ = qualname


@t.overload
def frozendict() -> t.Dict[t.Any, t.Any]:
    """Return empty MappingProxyType object."""


@t.overload
def frozendict(dct: T) -> T:
    """Return MappingProxyType object."""


def frozendict(dct: T = _NULL) -> T:
    """Get MappingProxyType object and correct typing (for TypedDict)."""
    if dct is _NULL:
        return MappingProxyType({})  # type: ignore
    return MappingProxyType(dct)  # type: ignore


# inspect


overload_dummy = t.overload(lambda: ...)


class T_NamedTuple(te.Protocol):
    _fields: t.Tuple[str, ...]
    _field_defaults: t.Dict[str, t.Any]


def isnamedtuple(typ: type) -> te.TypeGuard[T_NamedTuple]:
    """Check if class is explicit `typing.NamedTuple`."""
    if not isinstance(typ, type):
        return False
    if NamedTuple in getattr(typ, "__orig_bases__", ()):
        return True
    return False


def ismetaclass(cls: type) -> bool:
    return type in cls.__mro__


def isextbuiltin(obj: BuiltinFunctionType, name: str) -> bool:
    module = obj.__module__  # maybe None
    return bool(module and module.partition(".")[0] == name.partition(".")[0])


def getmodulename(path: str) -> t.Optional[str]:
    """Reimplement `inspect.getmodulename` for identifier modulename."""
    fn = os.path.basename(path)
    left, dot, right = fn.partition(".")
    if dot and left.isidentifier() and "." + right in all_suffixes():
        return left
    return None


def find_name_in_mro(cls: type, name: str, default: t.Any) -> t.Any:
    for base in cls.__mro__:
        if name in vars(base):
            return vars(base)[name]
    return default


def determind_varname(obj: t.Union[type, FunctionType]) -> str:
    # Maybe implement in AST analysis
    module = sys.modules[obj.__module__]
    for name, value in module.__dict__.items():
        if obj is value:
            return name
    raise RuntimeError(
        "could not determine where the object located. "
        f"object: {obj!r} __module__: {obj.__module__} __qualname__: {obj.__qualname__}"
    )


# TODO: extract function arguments without body
def findparamsource(obj: FunctionType) -> str:
    ...


# Utilities


def transform_dict_value(
    dct: t.Dict[KT, T], transformer: t.Callable[[T], TT]
) -> t.Dict[KT, TT]:
    return dict(zip(dct.keys(), map(transformer, dct.values())))


def dedent(s: str) -> str:
    """Enhanced version of `textwrap.dedent`.

    * Pretty better preformance (powered by pytest-benchmark).
    """
    lines = s.split("\n")  # splitlines will ignore the last newline
    margin = float("inf")
    for line in lines:
        if line:
            margin = min(margin, len(line) - len(line.lstrip()))
    # margin is only inf in case string empty
    if isinstance(margin, float):
        return s
    for i in range(len(lines)):
        lines[i] = lines[i][margin:]
    return "\n".join(lines)


def cleandoc(s: str, strict: bool = False) -> str:
    """Enhanced version of `inspect.cleandoc`.

    * Fix `inspect.cleandoc` do not remove space only lines (strict mode).
    * Slightly better performance (powered by pytest-benchmark).
    """
    lines = s.strip().expandtabs().splitlines()
    if strict:
        if any(line.isspace() for line in lines):
            raise ValueError
    margin = len(lines[-1]) - len(lines[-1].lstrip())
    for line in lines[1:]:
        if line:
            margin = min(margin, len(line) - len(line.lstrip()))
    for i in range(1, len(lines)):
        lines[i] = lines[i][margin:]
    return "\n".join(lines)


def typed_lru_cache(maxsize: int = 128, typed: bool = False) -> t.Callable[[T], T]:
    ...


# `lru_cache` has no type hint, so trick the linter
typed_lru_cache = __import__("functools").lru_cache


class cached_property(t.Generic[T, TT]):
    """Backport cached_property for py3.7 and lower."""

    def __init__(self, func: t.Callable[[T], TT]) -> None:
        self.func = func
        self.attrname = func.__name__
        self.__doc__ = func.__doc__

    def __set_name__(self, owner: T, name: str) -> None:
        # decorator always same name
        if name != self.attrname:
            # assignment should keep same name
            raise TypeError(
                f"cannot assign the cached_property named {self.attrname!r} to {name!r}"
            )

    def __get__(self, instance: t.Optional[T], owner: t.Type[T]) -> TT:
        if instance is None:
            return self  # type: ignore
        try:
            cache = instance.__dict__
        except AttributeError:  # not all objects have __dict__ (e.g. class defines slots)
            msg = (
                f"No '__dict__' attribute on {type(instance).__name__!r} "
                f"instance to cache {self.attrname!r} property."
            )
            raise TypeError(msg) from None
        try:
            val = cache[self.attrname]
        except KeyError:
            val = self.func(instance)
            cache[self.attrname] = val
        return val
