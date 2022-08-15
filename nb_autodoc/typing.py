from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from nb_autodoc.inspector import Class, Function, Variable


T_Annot = object
T_ModuleMember = Union["Class", "Function", "Variable"]
T_ClassMember = Union["Function", "Variable"]
