import logging
import re
import sys
import types
from typing import (
    Any,
    Callable,
    Dict,
    ForwardRef,
    Generic,
    Optional,
    Type,
    TypeVar,
    Union,
    cast,
)

from nb_autodoc.typing import T_Annot, T_GenericAlias, Tp_GenericAlias

T = TypeVar("T")
TT = TypeVar("TT")


logger = logging.getLogger("nb_autodoc")
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
logger.addHandler(console_handler)


def find_name_in_mro(cls: type, name: str, default: Any) -> Any:
    for base in cls.__mro__:
        if name in vars(base):
            return vars(base)[name]
    return default


def formatannotation(annot: T_Annot) -> str:
    """ForwardRef will be replaced to quoted name."""
    if annot is None or annot is type(None):
        return "None"
    elif isinstance(annot, str):
        return annot
    module = getattr(annot, "__module__", "")
    top_module = module.split(".", 1)[0]
    if module == "typing":
        if getattr(annot, "__qualname__", "") == "NewType.<locals>.new_type":
            return annot.__name__
        annot = repr(annot).replace("typing.", "")
    if top_module == "nptyping":
        return repr(annot)
    if isinstance(annot, type):
        if annot.__module__ == "builtins":
            return annot.__qualname__
        return annot.__module__ + "." + annot.__qualname__
    annot = re.sub(
        r"\b(typing\.)?ForwardRef\((?P<quot>[\"\'])(?P<str>.*?)(?P=quot)\)",
        r"\g<str>",
        annot,
    )
    return annot


def eval_annot_as_possible(
    t: Union[ForwardRef, T_GenericAlias, Any],
    globalns: Optional[Dict[str, Any]] = None,
    msg: str = "",
) -> Any:
    if globalns is None:
        globalns = {}
    if isinstance(t, ForwardRef):
        # _eval_type and _evaluate is breaking too much, just try eval
        try:
            return eval(t.__forward_code__, globalns)
        except Exception:
            logger.error(f"on {t}: {msg}")
        return t
    if isinstance(t, Tp_GenericAlias):
        t = cast(T_GenericAlias, t)
        ev_args = tuple(eval_annot_as_possible(a, globalns) for a in t.__args__)
        if ev_args == t.__args__:
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


class cached_property(Generic[T, TT]):
    def __init__(self, func: Callable[[T], TT]) -> None:
        self.func = func
        self.attrname: Optional[str] = None
        self.__doc__ = func.__doc__

    def __set_name__(self, owner: T, name: str) -> None:
        if self.attrname is None:
            self.attrname = name
        elif name != self.attrname:
            raise TypeError(
                "Cannot assign the same cached_property to two different names "
                f"({self.attrname!r} and {name!r})."
            )

    def __get__(self, instance: Optional[T], owner: Type[T]) -> TT:
        if instance is None:
            return self  # type: ignore
        if self.attrname is None:
            raise TypeError(
                "Cannot use cached_property instance without calling __set_name__ on it."
            )
        try:
            cache = instance.__dict__
        except AttributeError:  # not all objects have __dict__ (e.g. class defines slots)
            msg = (
                f"No '__dict__' attribute on {type(instance).__name__!r} "
                f"instance to cache {self.attrname!r} property."
            )
            raise TypeError(msg) from None
        val: TT
        try:
            val = cache[self.attrname]
        except KeyError:
            val = self.func(instance)
            cache[self.attrname] = val
        return val
