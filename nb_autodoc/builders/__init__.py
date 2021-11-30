"""
Documentation builder.
"""
import abc
import inspect
from pathlib import Path
from typing import Iterable, List, Tuple, NamedTuple

from nb_autodoc import Module, Class, Function, Variable, LibraryAttr
from nb_autodoc import schema, utils
from nb_autodoc.builders.parser.google import Docstring, get_dsobj


def resolve_dsobj_from_signature(
    dsobj: Docstring, signature: inspect.Signature
) -> Docstring:
    params: List[schema.DocstringParam] = []
    for p in signature.parameters.values():
        if p.name == "self":
            continue
        params.append(
            schema.DocstringParam(
                name=p.name, annotation=utils.formatannotation(p.annotation)
            )
        )
    save_docstring = {
        arg.name: (arg.version, arg.description) for arg in dsobj.args.content
    }
    for param in params:
        param.version, param.description = save_docstring.get(param.name, (None, None))
    dsobj.args.content = params
    if not dsobj.returns:
        return_anno = signature.return_annotation
        if return_anno is inspect.Signature.empty:
            dsobj.returns.source = "Unknown"
        else:
            dsobj.returns.source = utils.formatannotation(return_anno)
    return dsobj


class DocstringOverloads(NamedTuple):
    args: List[schema.DocstringSection]
    returns: List[schema.DocstringSection]


class Builder(abc.ABC):
    """Build documentation.

    Resolve the python objects with its docstring to a docstring object.

    The class inherits from this should implement the render of docstring object.
    Call method `write` to build module's documentation recursively.

    Args:
        dmodule: the Module with correct public object.
        output_dir: documentation output directory.
    """

    def __init__(self, dmodule: Module, *, output_dir: str) -> None:
        self.dmodule = dmodule
        self.output_dir = output_dir

    def variable_docstrings(self) -> Iterable[Tuple[Variable, Docstring]]:
        for dobj in self.dmodule.variables():
            dsobj = get_dsobj(dobj.docstring, "variable")
            yield dobj, dsobj

    def function_docstrings(self) -> Iterable[Tuple[Function, Docstring]]:
        for dobj in self.dmodule.functions():
            dsobj = get_dsobj(dobj.docstring, "function")
            signature = utils.get_signature(dobj.obj)
            dsobj = resolve_dsobj_from_signature(dsobj, signature)
            if dobj.overloads:
                myoverloads = DocstringOverloads(args=[], returns=[])
                for overload in dobj.overloads:
                    overload_dsobj = get_dsobj(overload.docstring)
                    overload_dsobj = resolve_dsobj_from_signature(
                        overload_dsobj, overload.signature
                    )
                    myoverloads.args.append(overload_dsobj.args)
                    myoverloads.returns.append(overload_dsobj.returns)
                dsobj.patch["overloads"] = myoverloads
            yield dobj, dsobj

    def class_docstrings(self) -> Iterable[Tuple[Class, Docstring]]:
        for dobj in self.dmodule.classes():
            dsobj = get_dsobj(dobj.docstring, "class")
            init_signature = utils.get_signature(dobj.obj)
            dsobj = resolve_dsobj_from_signature(dsobj, init_signature)
            yield dobj, dsobj

    def libraryattr_docstrings(self) -> Iterable[Tuple[LibraryAttr, Docstring]]:
        for dobj in self.dmodule.libraryattrs():
            dsobj = get_dsobj(dobj.docstring)
            yield dobj, dsobj

    def write(self) -> None:
        """Generic writer implementation."""
        filepath = Path(self.output_dir, *self.dmodule.refname.split("."))
        filepath.touch(exist_ok=True)
        with open(filepath, "w") as f:
            f.write(self.text())
        for submod in self.dmodule.submodules():
            self.__class__(submod, output_dir=self.output_dir).write()

    @abc.abstractmethod
    def text(self) -> str:
        """Get string of documentation."""
        raise NotImplementedError
