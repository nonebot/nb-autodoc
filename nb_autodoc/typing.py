import sys

if sys.version_info >= (3, 9):
    from types import GenericAlias

from typing import TYPE_CHECKING, Any, Tuple, Union
from typing_extensions import Protocol, TypeAlias, TypeGuard

if TYPE_CHECKING:
    from nb_autodoc.manager import (
        Class,
        EnumMember,
        Function,
        LibraryAttr,
        Variable,
        WeakReference,
    )

typing_GenericAlias = __import__("typing")._GenericAlias


class T_GenericAlias(Protocol):
    """`Union[typing._GenericAlias, types.GenericAlias]`."""

    __args__: Tuple[Any, ...]
    __parameters__: Tuple[Any, ...]
    __origin__: Any

    def __getitem__(self, __k: Any) -> "T_GenericAlias":
        ...


T_Annot = Union[T_GenericAlias, type, str, None]


def isgenericalias(obj: Any) -> TypeGuard[T_GenericAlias]:
    if sys.version_info >= (3, 9):
        return isinstance(obj, (GenericAlias, typing_GenericAlias))
    return isinstance(obj, typing_GenericAlias)


T_ValidMember = Union["T_ModuleMember", "T_ClassMember"]
T_ModuleMember = Union[
    "Class",
    "Function",
    "Variable",
    "WeakReference",
    "LibraryAttr",
]
T_ClassMember = Union["Function", "Variable", "EnumMember"]

T_Autodoc: TypeAlias = "dict[str, bool | str]"
