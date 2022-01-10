from typing import List, Optional, Union
from textwrap import indent

from nb_autodoc import schema, Doc, Class, Function, Variable, LibraryAttr
from nb_autodoc.builders import Builder, DocstringOverload
from nb_autodoc.builders.helpers import linkify
from nb_autodoc.builders.parser.google import Docstring, SINGULAR, MULTIPLE


def get_version(
    obj: Union["SINGULAR", Docstring, schema.DocstringSection, schema.DocstringParam],
    *,
    prefix: str = " ",
) -> str:
    ver = obj if isinstance(obj, str) else None
    if isinstance(obj, (Docstring, schema.DocstringSection)):
        ver = obj.version
    elif isinstance(obj, schema.DocstringParam):
        ver = obj.version
    if not ver:
        return ""
    if ver.endswith("-"):
        return f'{prefix}<Badge text="{ver}" type="error"/>'
    else:
        return f'{prefix}<Badge text="{ver}"/>'


class MarkdownBuilder(Builder):
    def text(self) -> str:
        builder: List[str] = []
        builder.append("---\n" "contentSidebar: true\n" "sidebarDepth: 0\n" "---")
        heading = "命名空间" if self.dmodule.is_namespace else "模块"
        dsobj = self.get_module_docstring()
        builder.append(f"# `{self.dmodule.refname}` {heading}{get_version(dsobj)}")
        if dsobj.description:
            builder.append(dsobj.description)
        for dobj, dsobj in self.iter_documentation_attrs():
            self.current_dobj = dobj
            if (
                isinstance(dobj, Variable)
                and not dsobj.description
                and not dobj.type_annotation
            ):
                continue
            builder.append(
                getattr(self, "render_" + dobj.__class__.__name__)(dobj, dsobj)
            )
        return "\n\n".join(builder)

    def add_link(self, dobj: Doc) -> str:
        return "[{}]({}#{})".format(
            dobj.qualname,
            self.uri_factory(dobj.module.refname, dobj.module.is_package),
            dobj.heading_id,
        )

    def render_params(
        self, params: List[schema.DocstringParam], level: int = 1, /
    ) -> str:
        text = "\n\n".join(
            "- `{name}`{annotation}{version}{desc}{long_desc}".format(
                name=p.name,
                annotation=" ({})".format(
                    linkify(
                        p.annotation,
                        add_link=self.add_link,
                        context=self.dmodule.context,
                    )
                )
                if p.annotation
                else "",
                version=get_version(p),
                desc=(p.description or "") and f": {p.description}",  # noqa
                long_desc="\n" + indent(p.long_description, prefix=" " * 4)
                if p.long_description
                else "",
            )
            for p in params
        )
        return indent(text, prefix=" " * level * 4)

    def render_Variable(self, dobj: Variable, dsobj: "Docstring") -> str:
        builder: List[str] = []
        section: Union[SINGULAR, MULTIPLE]
        ftitle = "## _{}_ `{}`{}"
        if dobj.cls is not None:
            ftitle = "#" + ftitle
        builder.append(
            ftitle.format(dobj.kind, dobj.name, get_version(dsobj))
            + f" {{#{dobj.heading_id}}}"
        )
        builder.append(
            f"- **类型:** {dobj.type_annotation}{get_version(dsobj.type_version)}"
        )
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

    def render_Function(self, dobj: Function, dsobj: "Docstring") -> str:
        builder: List[str] = []
        section: Union[SINGULAR, MULTIPLE]
        overloads: Optional[List[DocstringOverload]]
        ftitle = "## _{}_ `{}`{}"
        if dobj.cls is not None:
            ftitle = "#" + ftitle
        builder.append(
            ftitle.format(dobj.kind, dobj.name + dobj.params(), get_version(dsobj))
            + f" {{#{dobj.heading_id}}}"
        )
        if dsobj.description:
            builder.append("- **说明**")
            builder.append(dsobj.description)
        if section := dsobj.require:
            builder.append(f"- **要求**")
            builder.append(section)
        if overloads := dsobj.patch.get("overloads"):
            builder.append("- **重载**")
            for i, overload in enumerate(overloads):
                builder.append(f"    {i + 1}. `{overload.signature}`")
                builder.append("    参数")
                builder.append(self.render_params(overload.args.content, 2))
                builder.append("    返回")
                builder.append(self.render_params(overload.returns.content, 2))
        else:
            if dsobj.args.content:
                builder.append(f"- **参数**{get_version(dsobj.args)}")
                builder.append(self.render_params(dsobj.args.content))
            builder.append(f"- **返回**{get_version(dsobj.returns)}")
            builder.append(self.render_params(dsobj.returns.content))
        if section := dsobj.raises:
            builder.append(f"- **异常**{get_version(section)}")
            builder.append(
                self.render_params(section.content)
                or indent(section.source, prefix="    ")
            )
        if section := dsobj.examples:
            builder.append("- **用法**")
            builder.append(section)
        return "\n\n".join(builder)

    def render_Class(self, dobj: Class, dsobj: "Docstring") -> str:
        builder: List[str] = []
        section: Union[SINGULAR, MULTIPLE]
        builder.append(
            "## _{}_ `{}`{}".format(
                dobj.kind, dobj.name + dobj.params(), get_version(dsobj)
            )
            + f" {{#{dobj.heading_id}}}"
        )
        if dsobj.description:
            builder.append("- **说明**")
            builder.append(dsobj.description)
        if section := dsobj.require:
            builder.append(f"- **要求**")
            builder.append(section)
        if section := dsobj.args:
            if section.content:
                builder.append(f"- **参数**{get_version(section)}")
                builder.append(self.render_params(section.content))
        if section := dsobj.examples:
            builder.append("- **用法**")
            builder.append(section)
        return "\n\n".join(builder)

    def render_LibraryAttr(self, dobj: LibraryAttr, dsobj: "Docstring") -> str:
        builder: List[str] = []
        builder.append(f"## _{dobj.kind}_ `{dobj.name}`")
        builder.append("- **说明**")
        builder.append(dobj.docstring or "暂无文档")
        return "\n\n".join(builder)
