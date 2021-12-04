"""
Documentation builder.
"""
import abc
import inspect
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Tuple, NamedTuple

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
    if not dsobj.returns.content:
        return_anno = signature.return_annotation
        dsobj.returns.content.append(
            schema.DocstringParam(
                utils.formatannotation(return_anno)
                if not return_anno is inspect.Signature.empty
                else "Unknown",
                description=dsobj.returns.source,
            )
        )
    return dsobj


class DocstringOverload(NamedTuple):
    signature: str
    args: schema.DocstringSection
    returns: schema.DocstringSection


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
                myoverloads: List[DocstringOverload] = []
                for overload in dobj.overloads:
                    overload_dsobj = get_dsobj(overload.docstring)
                    overload_dsobj = resolve_dsobj_from_signature(
                        overload_dsobj, overload.signature
                    )
                    key = utils.signature_repr(overload.signature)
                    myoverloads.append(
                        DocstringOverload(
                            signature=key,
                            args=overload_dsobj.args,
                            returns=overload_dsobj.returns,
                        ),
                    )
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

    def module_docstring(self) -> Docstring:
        return get_dsobj(self.dmodule.docstring)

    def write(self) -> None:
        """Generic writer implementation."""
        path = Path(self.output_dir, *self.dmodule.refname.split("."))
        if self.dmodule.is_package:
            shutil.rmtree(path, ignore_errors=True)
            path.mkdir(parents=True, exist_ok=True)
            filepath = path / "index.md"
        else:
            filepath = path.with_suffix(".md")
        if not self.dmodule.is_namespace:
            filepath.touch(exist_ok=False)
            with open(filepath, "w") as f:
                f.write(self.text())
        for submod in self.dmodule.submodules():
            self.__class__(submod, output_dir=self.output_dir).write()

    @abc.abstractmethod
    def text(self) -> str:
        """Get string of documentation."""
        raise NotImplementedError
