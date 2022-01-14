"""
Documentation builder.
"""
import abc
import inspect
import shutil
from pathlib import Path
from typing import Callable, Iterable, List, Tuple, NamedTuple, Union

from nb_autodoc import Module, Class, Function, Variable, LibraryAttr
from nb_autodoc import schema, utils
from nb_autodoc.builders.parser.google import Docstring, get_dsobj


def default_path_factory(refname: str, ispkg: bool) -> Path:
    """Default path factory for markdown."""
    path = Path(*refname.split("."))
    if ispkg:
        filepath = path / "index.md"
    else:
        filepath = path.with_suffix(".md")
    return filepath


def default_uri_factory(refname: str, ispkg: bool) -> str:
    """Default uri factory for html."""
    uri = refname.replace(".", "/")
    to_strip = refname.split(".", 1)[0]
    if ispkg:
        uri += "/index.md"
    else:
        uri += ".md"
    return uri.lstrip(to_strip + "/")


def resolve_dsobj_from_signature(
    dsobj: Docstring, signature: inspect.Signature, *, no_returns: bool = False
) -> Docstring:
    params: List[schema.DocstringParam] = []
    dparams_dict = {dp.name: dp for dp in dsobj.args.content}
    extra_params = dparams_dict.keys() - signature.parameters.keys()

    for dp in dsobj.args.content:
        if dp.annotation:
            dp.annotation = utils.convert_anno_new_style(dp.annotation)

    for p in signature.parameters.values():
        if p.name == "self" or p.name == "cls":
            # BUG: maybe not these common name
            continue
        dp = dparams_dict.get(p.name) or schema.DocstringParam(
            name=p.name, annotation=utils.formatannotation(p.annotation)
        )
        if p.kind is inspect.Parameter.VAR_POSITIONAL:
            dp.name = "*" + p.name
        elif p.kind is inspect.Parameter.VAR_KEYWORD:
            dp.name = "**" + p.name
        if not dp.annotation:
            dp.annotation = utils.formatannotation(p.annotation)
        params.append(dp)

    for name in extra_params:
        dp = dparams_dict[name]
        if dp.annotation:
            dp.annotation = utils.convert_anno_new_style(dp.annotation)
        params.append(dp)
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
        else:
            for dp in dsobj.returns.content:
                dp.name = utils.convert_anno_new_style(dp.name)

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
    """

    def __init__(
        self,
        dmodule: Module,
        *,
        output_dir: str,
        path_factory: Callable[[str, bool], Path] = default_path_factory,
        uri_factory: Callable[[str, bool], str] = default_uri_factory,
    ) -> None:
        """
        Args:
            dmodule: the documentation module.
            output_dir: documentation output directory.
            path_factory: construct local filename relative to `output_dir`.
                    Receive two positional_only parameters (`refname`, `ispkg`).
                    Return `filepath`.
            uri_factory: specify the resource location on internet.
                    Receive two positional_only parameters (`refname`, `qualname`).
                    Return `uri`.
        """
        self.dmodule: Module = dmodule
        self.output_dir: str = output_dir
        self.path_factory: Callable[[str, bool], Path] = path_factory
        self.uri_factory: Callable[[str, bool], str] = uri_factory

    @staticmethod
    def get_docstring(dobj: Union[Variable, Function, Class, LibraryAttr]) -> Docstring:
        if isinstance(dobj, Variable):
            return get_dsobj(dobj.docstring, Docstring.VARIABLE)
        elif isinstance(dobj, Function):
            dsobj = get_dsobj(dobj.docstring, Docstring.FUNCTION)
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
            dsobj = get_dsobj(dobj.docstring, Docstring.CLASS)
            init_signature = utils.get_signature(dobj.obj)
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
        buildpath = Path(self.output_dir).resolve()
        filepath = buildpath / self.path_factory(
            self.dmodule.refname, self.dmodule.is_package
        )
        if not self.dmodule.supermodule:
            shutil.rmtree(filepath.parent, ignore_errors=True)
        if self.dmodule.is_package:
            filepath.parent.mkdir(parents=True, exist_ok=True)
        if not self.dmodule.is_namespace:
            filepath.touch(exist_ok=False)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(self.text())
        for submod in self.dmodule.submodules():
            self.__class__(
                submod,
                output_dir=self.output_dir,
                path_factory=self.path_factory,
                uri_factory=self.uri_factory,
            ).write()

    @abc.abstractmethod
    def text(self) -> str:
        """Get string of current module documentation."""
        raise NotImplementedError
