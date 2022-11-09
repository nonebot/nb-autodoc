from typing import TYPE_CHECKING, Any, Tuple, Union
from typing_extensions import Protocol, TypeAlias

if TYPE_CHECKING:
    from nb_autodoc.analyzers.definitionfinder import (
        AssignData,
        ClassDefData,
        FunctionDefData,
        ImportFromData,
    )
    from nb_autodoc.manager import (
        Class,
        EnumMember,
        Function,
        LibraryAttr,
        Variable,
        WeakReference,
    )


class T_GenericAlias(Protocol):
    """`Union[typing._GenericAlias, types.GenericAlias]`.

    Instance check on this class may cause ambitious problems, check from
    `Tp_GenericAlias` directly.
    """

    __args__: Tuple[Any, ...]
    __parameters__: Tuple[Any, ...]
    __origin__: Any


T_Annot = Union[T_GenericAlias, type, str, None]


T_ValidMember = Union["T_ModuleMember", "T_ClassMember"]
T_ModuleMember = Union[
    "Class",
    "Function",
    "Variable",
    "WeakReference",
    "LibraryAttr",
]
T_ClassMember = Union["Function", "Variable", "EnumMember"]

T_ASTMember = Union["AssignData", "FunctionDefData", "ClassDefData", "ImportFromData"]

T_Autodoc: TypeAlias = "dict[str, bool | str]"
