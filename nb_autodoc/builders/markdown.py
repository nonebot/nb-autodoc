from typing import List, Optional, Union, TYPE_CHECKING
from textwrap import indent

from nb_autodoc import schema
from nb_autodoc import Class, Function, Variable, LibraryAttr
from nb_autodoc.builders import Builder, DocstringOverload
from nb_autodoc.builders.helpers import get_title
from nb_autodoc.schema.docstring import DocstringParam

if TYPE_CHECKING:
    from nb_autodoc.builders.parser.google import Docstring, SINGULAR, MULTIPLE


def get_version(
    obj: Union["SINGULAR", "Docstring", schema.DocstringSection, schema.DocstringParam],
    *,
    prefix: str = " ",
) -> str:
    ver = obj if isinstance(obj, str) or obj is None else obj.version
    if not ver:
        return ""
    if ver.endswith("-"):
        return f'{prefix}<Badge text="{ver}" type="error"/>'
    else:
        return f'{prefix}<Badge text="{ver}"/>'


def render_params(params: List[DocstringParam], ident: int = 4, /) -> str:
    return "\n\n".join(
        "{spaces}- `{name}`{annotation}{version}{description}".format(
            spaces=" " * ident,
            name=p.name,
            annotation=(p.annotation or "") and f" ({p.annotation})",
            version=get_version(p),
            description=(p.description or "") and f": {p.description}",
        )
        for p in params
    )


def render_variable(dobj: Variable, dsobj: "Docstring") -> str:
    builder: List[str] = []
    section: Union[SINGULAR, MULTIPLE]
    if dobj.cls:
        builder.append(f"### {get_title(dobj)}{get_version(dsobj)}")
    else:
        builder.append(f"## {get_title(dobj)}{get_version(dsobj)}")
    builder.append(f"- **类型:** {dobj.type_annotation}{get_version(dsobj.type_version)}")
    if dsobj.description:
        if "\n" in dsobj.description:
            builder.append("- **说明**")
            builder.append(dsobj.description)
        else:
            builder.append(f"- **说明:** {dsobj.description}")
    if section := dsobj.examples:
        builder.append("- **用法**")
        builder.append(section)
    return "\n\n".join(builder)


def render_function(dobj: Function, dsobj: "Docstring") -> str:
    builder: List[str] = []
    section: Union[SINGULAR, MULTIPLE]
    overloads: Optional[List[DocstringOverload]]
    if dobj.cls:
        builder.append(f"### {get_title(dobj)}{get_version(dsobj)}")
    else:
        builder.append(f"## {get_title(dobj)}{get_version(dsobj)}")
    if dsobj.description:
        builder.append("- **说明**")
        builder.append(dsobj.description)
    if section := dsobj.require:
        builder.append(f"- **要求**{get_version(section)}")
        builder.append(section)
    if overloads := dsobj.patch.get("overloads"):
        builder.append("- **重载**")
        for i, overload in enumerate(overloads):
            builder.append(f"    {i + 1}. `{overload.signature}`")
            builder.append("    参数")
            builder.append(render_params(overload.args.content, 8))
            builder.append("    返回")
            builder.append(render_params(overload.returns.content, 8))
    else:
        builder.append(f"- **参数**{get_version(dsobj.args)}")
        builder.append(render_params(dsobj.args.content) or "    无")
        builder.append(f"- **返回**{get_version(dsobj.returns)}")
        builder.append(render_params(dsobj.returns.content))
    if section := dsobj.raises:
        builder.append(f"- **异常**{get_version(section)}")
        builder.append(
            render_params(section.content) or indent(section.source, prefix="    ")
        )
    if section := dsobj.examples:
        builder.append("- **用法**")
        builder.append(section)
    return "\n\n".join(builder)


def render_class(dobj: Class, dsobj: "Docstring") -> str:
    builder: List[str] = []
    section: Union[SINGULAR, MULTIPLE]
    builder.append(f"## {get_title(dobj)}{get_version(dsobj)}")
    if dsobj.description:
        builder.append("- **说明**")
        builder.append(dsobj.description)
    if section := dsobj.require:
        builder.append(f"- **要求**{get_version(section)}")
        builder.append(section)
    if section := dsobj.args:
        if section.content:
            builder.append(f"- **参数**{get_version(section)}")
            builder.append(render_params(section.content))
    if section := dsobj.examples:
        builder.append("- **用法**")
        builder.append(section)
    return "\n\n".join(builder)


def render_libraryattr(dobj: LibraryAttr, dsobj: "Docstring") -> str:
    builder: List[str] = []
    builder.append(f"## {get_title(dobj)}")
    builder.append("- **说明**")
    builder.append(dobj.docstring or "暂无文档")
    return "\n\n".join(builder)


class MarkdownBuilder(Builder):
    def text(self) -> str:
        builder: List[str] = []
        heading = "命名空间" if self.dmodule.is_namespace else "模块"
        dsobj = self.get_module_docstring()
        builder.append(f"# `{self.dmodule.refname}` {heading}{get_version(dsobj)}")
        if self.dmodule.docstring:
            builder.append(self.dmodule.docstring)
        for dobj, dsobj in self.iter_documentation_attrs():
            if isinstance(dobj, Variable):
                builder.append(render_variable(dobj, dsobj))
            elif isinstance(dobj, Function):
                builder.append(render_function(dobj, dsobj))
            elif isinstance(dobj, Class):
                builder.append(render_class(dobj, dsobj))
            elif isinstance(dobj, LibraryAttr):
                builder.append(render_libraryattr(dobj, dsobj))
        return "\n\n".join(builder)
