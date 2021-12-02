from typing import Dict, List, Optional, Union, TYPE_CHECKING
from textwrap import indent

from nb_autodoc import schema
from nb_autodoc import Module, Class, Function, Variable, LibraryAttr
from nb_autodoc.builders import Builder, DocstringOverload
from nb_autodoc.builders.helpers import get_title
from nb_autodoc.schema.docstring import DocstringParam

if TYPE_CHECKING:
    from nb_autodoc.builders.parser.google import Docstring, SINGULAR, MULTIPLE


def get_if_exists(s: Optional[str], template: str, /) -> str:
    if not s:
        return ""
    return template.format(s)


def get_version(
    obj: Union[str, "Docstring", schema.DocstringSection, schema.DocstringParam],
    *,
    prefix: str = " ",
) -> str:
    ver = obj if isinstance(obj, str) else obj.version
    if not ver:
        return ""
    if ver.endswith("-"):
        fver = '{}<Badge text="{}" type="error"/>'
    else:
        fver = '{}<Badge text="{}"/>'
    return fver.format(prefix, ver)


def get_param(p: DocstringParam, ident: int = 4, /) -> str:
    return "{spaces}{name}{annotation}{version}{description}".format(
        spaces=" " * ident,
        name=p.name,
        annotation=get_if_exists(p.annotation, " ({})"),
        version=get_version(p),
        description=get_if_exists(p.description, ": {}"),
    )


def render_function(dobj: Function, dsobj: "Docstring", /) -> str:
    builder: List[str] = []
    section: Union[SINGULAR, MULTIPLE]
    overloads: Optional[Dict[str, DocstringOverload]]
    builder.append(f"## {get_title(dobj)}{get_version(dsobj)}")
    if dsobj.description:
        builder.append("- **说明**")
        builder.append(dsobj.description)
    if section := dsobj.require:
        builder.append(f"- **要求**{get_version(section)}")
        builder.append(indent(section, prefix="    "))
    if overloads := dsobj.patch.get("overloads"):
        builder.append("- **重载**")
        for i, (title, overload) in enumerate(overloads.items()):
            builder.append(f"    {i + 1}. `{title}`")
            builder.append("    参数")
            for param in overload.args.content:
                builder.append(get_param(param, 8))
            builder.append("    返回")
            for param in overload.returns.content:
                builder.append(get_param(param, 8))
    else:
        builder.append(f"- **参数**{get_version(dsobj.args)}")
        for param in dsobj.args.content:
            builder.append(get_param(param))
        if not dsobj.args.content:
            builder.append("    无")
        builder.append(f"- **返回**{get_version(dsobj.returns)}")
        for param in dsobj.returns.content:
            builder.append(get_param(param))
    if section := dsobj.raises:
        builder.append(f"- **异常**{get_version(section)}")
        for param in section.content:
            builder.append(get_param(param))
        if not section.content:
            builder.append(indent(section.source, prefix="    "))
    if section := dsobj.examples:
        builder.append(f"- **用法**")
        builder.append(indent(section, prefix="    "))
    return "\n\n".join(builder)


class MarkdownBuilder(Builder):
    def text(self) -> str:
        builder: List[str] = []
        for dobj, dsobj in self.function_docstrings():
            rendered = render_function(dobj, dsobj)
            builder.append(str(rendered))
        return "\n\n".join(builder)
