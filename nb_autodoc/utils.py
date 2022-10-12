import ast
import os
import re
import sys
import types
import typing as t
from importlib.machinery import all_suffixes
from importlib.util import resolve_name as imp_resolve_name

from nb_autodoc.log import logger
from nb_autodoc.typing import T_Annot, T_GenericAlias, Tp_GenericAlias

T = t.TypeVar("T")
TT = t.TypeVar("TT")


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

    def __init_subclass__(cls, module: str, qualname: str) -> None:
        cls.__module__ = module
        cls.__qualname__ = qualname


@t.overload
def frozendict() -> t.Dict[t.Any, t.Any]:
    ...


@t.overload
def frozendict(dct: T) -> T:
    ...


def frozendict(dct: T = _NULL) -> T:
    """Get MappingProxyType and correct typing (for TypedDict)."""
    if dct is _NULL:
        return types.MappingProxyType({})  # type: ignore
    return types.MappingProxyType(dct)  # type: ignore


def resolve_name(
    name_or_import: t.Union[ast.ImportFrom, str], package: t.Optional[str] = None
) -> str:
    if isinstance(name_or_import, ast.ImportFrom):
        name_or_import = "." * name_or_import.level + (name_or_import.module or "")
    return imp_resolve_name(name_or_import, package)


# inspect


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


def determind_varname(obj: t.Union[type, types.FunctionType, types.MethodType]) -> str:
    # Maybe implement in AST analysis
    module = sys.modules[obj.__module__]
    for name, value in module.__dict__.items():
        if obj is value:
            return name
    raise RuntimeError(
        "could not determine where the object located. "
        f"object: {obj!r} __module__: {obj.__module__} __qualname__: {obj.__qualname__}"
    )


def _remove_typing_prefix(s: str) -> str:
    # see: https://github.com/python/cpython/issues/96073
    def repl(match: re.Match[str]) -> str:
        text = match.group()
        if text.startswith("typing."):
            return text[len("typing.") :]
        return text

    return re.sub(r"[\w\.]+", repl, s)


def _type_repr(
    obj: t.Any, type_alias: t.Dict[T_GenericAlias, str], msg: str = ""
) -> str:
    if obj in type_alias:
        return type_alias[obj]
    if obj is ...:  # Arg ellipsis is OK
        return "..."
    elif obj is type(None) or obj is None:
        return "None"
    elif isinstance(obj, str):
        # Possible in types.GenericAlias
        logger.warning(f"found bare string {obj!r} in __args__")
        return obj
    elif isinstance(obj, Tp_GenericAlias):
        # Annotated do not give a name
        if sys.version_info >= (3, 9) and isinstance(
            obj, getattr(t, "_AnnotatedAlias")
        ):
            return _type_repr(obj.__origin__, type_alias)
        if isinstance(obj.__origin__, t._SpecialForm):
            name = obj.__origin__._name  # type: ignore
        else:
            # Most ABCs and concrete type alias
            # Getattr to trick types.GenericAlias
            name = getattr(obj, "_name", None) or obj.__origin__.__name__
        if name == "Union":
            args = obj.__args__
            if len(args) == 2:
                if args[0] is type(None):
                    return f"Optional[{_type_repr(args[1], type_alias)}]"
                elif args[1] is type(None):
                    return f"Optional[{_type_repr(args[0], type_alias)}]"
        elif name == "Callable":
            if len(obj.__args__) == 2 and obj.__args__[0] is Ellipsis:
                return f"Callable[..., {_type_repr(obj.__args__[1], type_alias)}]"
            args = ", ".join(_type_repr(a, type_alias) for a in obj.__args__[:-1])
            rt = _type_repr(obj.__args__[-1], type_alias)
            return f"Callable[[{args}], {rt}]"
        args = ", ".join([_type_repr(a, type_alias) for a in obj.__args__])
        return f"{name}[{args}]"
    # The isinstance type should behind the types.GenericAlias check
    # Because list[int] is both type and GenericAlias subclass
    elif isinstance(obj, type):
        if obj.__module__ == "builtins":
            return obj.__qualname__
        if "<locals>" in obj.__qualname__:
            return f"{obj.__module__}.{determind_varname(obj)}"
        else:
            return f"{obj.__module__}.{obj.__qualname__}"
    elif isinstance(obj, t.TypeVar):
        return repr(obj)
    elif isinstance(obj, t.ForwardRef):
        logger.warning(msg + f"found unevaluated {obj}")
        return obj.__forward_arg__
    module = getattr(obj, "__module__", "")
    qualname = getattr(obj, "__qualname__", "")
    if module == "typing":
        if qualname == "NewType.<locals>.new_type":
            return obj.__name__
        logger.warning(msg + "unknown typing object, maybe a bug on nb_autodoc")
        return _remove_typing_prefix(repr(obj))
    raise TypeError(f"unexpected annotation type {type(obj)}")


def formatannotation(
    annot: T_Annot, type_alias: t.Dict[T_GenericAlias, str], msg: str = ""
) -> str:
    """Traverse __args__ and specify the type to represent.

    Give `type_alias` to specify the type's original reference.

    Raises:
        TypeError: annotation is invalid
    """
    if annot is ...:
        raise TypeError("ellipsis annotation is invalid")
    elif isinstance(annot, t.ForwardRef):
        logger.warning(msg + f"expect GenericAlias, got {annot}")
        return annot.__forward_arg__
    elif isinstance(annot, str):
        logger.warning(msg + f"expect GenericAlias, got bare string {annot!r}")
        return annot
    module = getattr(annot, "__module__", "")
    top_module = module.split(".", 1)[0]
    if top_module == "nptyping":
        return repr(annot)
    return _type_repr(annot, type_alias, msg)


def eval_annot_as_possible(
    tp: t.Union[t.ForwardRef, T_GenericAlias, t.Any],
    globalns: t.Optional[t.Dict[str, t.Any]] = None,
    msg: str = "",
) -> t.Any:
    if globalns is None:
        globalns = {}
    if isinstance(tp, t.ForwardRef):
        # _eval_type and _evaluate is breaking too much, just try eval
        try:
            return eval(tp.__forward_code__, globalns)
        except Exception:
            logger.error(f"on {t}: {msg}")
        return tp
    if isinstance(tp, Tp_GenericAlias):
        tp = t.cast(T_GenericAlias, tp)
        ev_args = tuple(eval_annot_as_possible(a, globalns) for a in tp.__args__)
        if ev_args == tp.__args__:
            return t
        if sys.version_info >= (3, 9) and isinstance(t, types.GenericAlias):
            return types.GenericAlias(t.__origin__, ev_args)
        else:
            return t.copy_with(ev_args)  # type: ignore
    return t  # Ellipsis


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
