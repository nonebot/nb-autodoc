"""
Documentation builder.
"""
import abc
import inspect
import shutil
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, NamedTuple, Union

from nb_autodoc import Module, Class, Function, Variable, LibraryAttr
from nb_autodoc import schema, utils
from nb_autodoc.builders.parser.google import Docstring, get_dsobj


def resolve_dsobj_from_signature(
    dsobj: Docstring, signature: inspect.Signature, *, no_returns: bool = False
) -> Docstring:
    params: List[schema.DocstringParam] = []
    var_positional: Optional[str] = None
    var_keyword: Optional[str] = None
    for p in signature.parameters.values():
        if p.kind is inspect.Parameter.VAR_POSITIONAL:
            var_positional = p.name
        elif p.kind is inspect.Parameter.VAR_KEYWORD:
            var_keyword = p.name
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
        if param.name == var_positional:
            param.name = "*" + param.name
        elif param.name == var_keyword:
            param.name = "**" + param.name
    dsobj.args.content = params
    if not no_returns:
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
        dmodule: the documentation module.
        output_dir: documentation output directory.
    """

    def __init__(self, dmodule: Module, *, output_dir: str) -> None:
        self.dmodule = dmodule
        self.output_dir = output_dir

    @staticmethod
    def get_docstring(dobj: Union[Variable, Function, Class, LibraryAttr]) -> Docstring:
        if isinstance(dobj, Variable):
            return get_dsobj(dobj.docstring, "variable")
        elif isinstance(dobj, Function):
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
                    myoverloads.append(
                        DocstringOverload(
                            signature=utils.signature_repr(overload.signature),
                            args=overload_dsobj.args,
                            returns=overload_dsobj.returns,
                        ),
                    )
                dsobj.patch["overloads"] = myoverloads
            return dsobj
        elif isinstance(dobj, Class):
            dsobj = get_dsobj(dobj.docstring, "class")
            init_signature = utils.get_signature(getattr(dobj.obj, "__init__"))
            dsobj = resolve_dsobj_from_signature(dsobj, init_signature, no_returns=True)
            return dsobj
        elif isinstance(dobj, LibraryAttr):
            return get_dsobj(dobj.docstring)

    def iter_documentation_attrs(
        self,
    ) -> Iterable[Tuple[Union[Variable, Function, Class, LibraryAttr], Docstring]]:
        """Yield all documentation object in order."""
        dobj: Union[Variable, Function, Class, LibraryAttr]
        cls_dobj: Union[Function, Variable]
        for dobj in self.dmodule.variables():
            yield dobj, self.get_docstring(dobj)
        for dobj in self.dmodule.functions():
            yield dobj, self.get_docstring(dobj)
        for dobj in self.dmodule.classes():
            yield dobj, self.get_docstring(dobj)
            for cls_dobj in dobj.variables():
                yield cls_dobj, self.get_docstring(cls_dobj)
            for cls_dobj in dobj.functions():
                yield cls_dobj, self.get_docstring(cls_dobj)
        for dobj in self.dmodule.libraryattrs():
            yield dobj, self.get_docstring(dobj)

    def get_module_docstring(self) -> Docstring:
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
        """Get string of current module documentation."""
        raise NotImplementedError
