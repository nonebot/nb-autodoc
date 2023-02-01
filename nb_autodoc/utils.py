import __future__ as _future

import os
import re
import sys
import typing as t
import typing_extensions as te
from enum import Enum
from importlib.machinery import all_suffixes
from inspect import Signature
from operator import attrgetter
from os.path import commonprefix
from pathlib import Path
from types import BuiltinFunctionType, FunctionType, MappingProxyType
from typing import NamedTuple

_co_future_flags = {"annotations": _future.annotations.compiler_flag}
del _future

T = t.TypeVar("T")
TT = t.TypeVar("TT")
KT = t.TypeVar("KT")


_NULL: t.Any = object()


def safe_getattr(obj: t.Any, *attrs: str, default: t.Any = _NULL) -> t.Any:
    """Safe getattr that turns all exception into AttributeError."""
    try:
        return attrgetter(*attrs)(obj)
    except Exception:
        if default is _NULL:
            raise AttributeError(f"{obj!r} has no attribute {attrs!r}") from None
        else:
            return default


def safe_evalattr(
    attr: str, globalns: t.Dict[str, t.Any], default: t.Any = _NULL
) -> t.Any:
    try:
        return eval(attr, globalns)
    except Exception:
        if default is _NULL:
            raise AttributeError
        else:
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
    """Return empty dict."""


@t.overload
def frozendict(dct: T) -> T:
    """Get MappingProxyType object and correct typing (for TypedDict)."""


def frozendict(dct: T = _NULL) -> T:
    # T should be bound on dict, but mypy mistake TypedDict
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


def isenumclass(cls: type) -> te.TypeGuard[t.Type[Enum]]:
    return issubclass(cls, Enum)


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
def findparamsource(obj: FunctionType) -> str:  # type: ignore  # mypy
    ...


def stringify_signature(
    sig: Signature, *, show_annotation: bool = False, show_returns: bool = False
) -> str:
    sig = sig.replace()
    params = sig.parameters.copy()
    if not show_annotation:
        for param in sig.parameters.values():
            params[param.name] = param.replace(annotation=Signature.empty)
    res = str(
        sig.replace(parameters=list(params.values()), return_annotation=Signature.empty)
    )
    if show_returns:
        ret = "<untyped>"
        if sig.return_annotation is not Signature.empty:
            # current internal annotation is fully static
            # so we don't need type_repr or formatannotation
            ret = str(sig.return_annotation)
        res += f" -> {ret}"
    return res


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
    lines = s.rstrip().expandtabs().splitlines()
    if strict:
        if any(line.isspace() for line in lines):
            raise ValueError
    margin = len(lines[-1]) - len(lines[-1].lstrip())
    for line in lines[1:-1]:
        if line:
            margin = min(margin, len(line) - len(line.lstrip()))
    for i in range(1, len(lines)):
        lines[i] = lines[i][margin:]
    while lines and not lines[0]:
        lines.pop(0)
    return "\n".join(lines)


def interleave(
    inter: t.Callable[[], None], f: t.Callable[[T], None], seq: t.Iterable[T]
) -> None:
    """Call f on each item in seq, calling inter() in between."""
    seq = iter(seq)
    try:
        f(next(seq))
    except StopIteration:
        pass
    else:
        for x in seq:
            inter()
            f(x)


def calculate_relpath(p1: Path, p2: Path) -> str:
    """Returns '../log' like `os.path.relpath('/usr/var/log', '/usr/var/sad')`."""
    # `pathlib.Path.relative_to` doesn't fully implement it
    pparts1 = p1.parts
    pparts2 = p2.parts
    lencommon = len(commonprefix([pparts1, pparts2]))
    builder = [".."] * (len(pparts2) - lencommon)
    builder.extend(pparts1[lencommon:])
    return "/".join(builder)


def cleanexpr(code: str) -> str:
    # this is incomplete, consider unparse
    code = code.strip()
    code = code.replace("\n", " ").replace("\r", " ")
    code = re.sub(r"\s+", " ", code)
    return code


def get_first_element(lst: t.List[t.Any], typ: t.Type[T]) -> t.Optional[T]:
    return next(
        filter(lambda x: isinstance(x, typ), lst),
        None,
    )


class cached_property(t.Generic[T]):
    """Backport cached_property for py3.7 and lower."""

    def __init__(self, func: t.Callable[[t.Any], T]) -> None:
        self.func = func
        self.attrname = func.__name__
        self.__doc__ = func.__doc__

    def __set_name__(self, owner: t.Any, name: str) -> None:
        # decorator always same name
        if name != self.attrname:
            # assignment should keep same name
            raise TypeError(
                f"cannot assign the cached_property named {self.attrname!r} to {name!r}"
            )

    def __get__(self, instance: t.Optional[t.Any], owner: t.Type[t.Any]) -> T:
        if instance is None:
            return self  # type: ignore
        try:
            cache = instance.__dict__
        except (
            AttributeError
        ):  # not all objects have __dict__ (e.g. class defines slots)
            msg = (
                f"No '__dict__' attribute on {type(instance).__name__!r} "
                f"instance to cache {self.attrname!r} property."
            )
            raise TypeError(msg) from None
        try:
            return cache[self.attrname]
        except KeyError:
            pass  # avoid extra traceback
        val = self.func(instance)
        cache[self.attrname] = val
        return val
