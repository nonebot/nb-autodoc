import logging
import re
import sys
import types
from typing import _AnnotatedAlias  # type: ignore
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
    _SpecialForm,
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


def _remove_typing_prefix(s: str) -> str:
    def repl(match: re.Match[str]) -> str:
        text = match.group()
        if text.startswith("typing."):
            return text[len("typing.") :]
        return text

    return re.sub(r"[\w\.]+", repl, s)


def _type_repr(obj: Any, type_alias: Dict[T_GenericAlias, str], msg: str = "") -> str:
    if obj in type_alias:
        return type_alias[obj]
    if obj is ...:  # Arg ellipsis is OK
        return "..."
    elif obj is type(None) or obj is None:
        return "None"
    elif isinstance(obj, str):
        # Possible in types.GenericAlias
        logger.warning(f"bare string type annotation {obj!r}")
        return obj
    elif isinstance(obj, Tp_GenericAlias):
        # Annotated do not give a name
        if sys.version_info >= (3, 9) and isinstance(obj, _AnnotatedAlias):
            return _type_repr(obj.__origin__, type_alias)
        if isinstance(obj.__origin__, _SpecialForm):
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
        return f"{obj.__module__}.{obj.__qualname__}"
    elif isinstance(obj, TypeVar):
        return repr(obj)
    elif isinstance(obj, ForwardRef):
        logger.warning(msg + f"bare string type annotation {obj.__forward_arg__!r}")
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
    annot: T_Annot, type_alias: Dict[T_GenericAlias, str], msg: str = ""
) -> str:
    """Traverse __args__ and specify the type to represent.

    Give `type_alias` to specify the type's original reference.

    Raises:
        TypeError: annotation is invalid
    """
    if annot is ...:
        raise TypeError("ellipsis annotation is invalid")
    elif isinstance(annot, ForwardRef):
        logger.warning(msg + "expect GenericAlias, got ForwardRef")
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
