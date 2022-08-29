import sys
import types
from typing import _GenericAlias  # type: ignore
from typing import TYPE_CHECKING, Any, Tuple, Union
from typing_extensions import Protocol

if TYPE_CHECKING:
    from nb_autodoc.manager import (
        Class,
        DynamicClassFunction,
        External,
        Function,
        LibraryAttr,
        Variable,
    )


class T_GenericAlias(Protocol):
    """`Union[typing._GenericAlias, types.GenericAlias]`.

    Instance check on this class may cause ambitious problems, check from
    `Tp_GenericAlias` directly.
    """

    __args__: Tuple[Any, ...]
    __parameters__: Tuple[Any, ...]
    __origin__: Any


T_Annot = Any
"""`Union[typing._GenericAlias, types.GenericAlias, type, str, None]`."""
T_ModuleMember = Union[
    "Class", "Function", "Variable", "External", "LibraryAttr", "DynamicClassFunction"
]
T_ClassMember = Union["Function", "Variable"]

if sys.version_info >= (3, 9):
    Tp_GenericAlias = (_GenericAlias, types.GenericAlias)
else:
    Tp_GenericAlias = _GenericAlias
