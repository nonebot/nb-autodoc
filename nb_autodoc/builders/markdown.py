import os
import re
from typing import Callable, List, Optional, Union
from textwrap import indent as _indent

from nb_autodoc import schema, Doc, Class, Function, Variable, LibraryAttr
from nb_autodoc.builders import Builder, DocstringOverload
from nb_autodoc.builders.helpers import linkify
from nb_autodoc.builders.parser.google import Docstring, DocstringSection


def get_version(
    obj: Union[
        Optional[str], Docstring, schema.DocstringSection, schema.DocstringParam
    ],
    *,
    prefix: str = " ",
) -> str:
    if isinstance(obj, (schema.DocstringParam, schema.DocstringSection)):
        ver = obj.version
    elif isinstance(obj, Docstring):
        ver = obj.version.source
        for id, content in obj.roles:
            if id == "version":
                ver = content
    else:
        ver = obj
    if not ver:
        return ""
    if ver.endswith("-"):
        return f'{prefix}<Badge text="{ver}" type="error"/>'
    else:
        return f'{prefix}<Badge text="{ver}"/>'


def get_title(dobj: Doc) -> str:
    body = dobj.name
    if isinstance(dobj, Class):
        if not dobj.kind == "enum":
            body += dobj.params()
    elif isinstance(dobj, Function):
        body += dobj.params()
    return f"_{dobj.kind}_ `{body}`"


def replace_description(s: str, repl: Callable[[re.Match], str]) -> str:
    return re.sub(
        r"{(?P<name>\w+?)}`(?:(?P<text>[^{}]+?) <)?(?P<content>[\w\.\+\-]+)(?(text)>)`",
        repl,
        s,
    )


class MarkdownBuilder(Builder):
    def text(self) -> str:
        self.current_filepath = self.uri_factory(
            self.dmodule.refname, self.dmodule.is_package
        )
        builder: List[str] = []
        dsobj = self.get_module_docstring()
        if dsobj.metadata:
            builder.append(f"---\n{dsobj.metadata.source}\n---")
        builder.append(f"# {self.dmodule.refname}{get_version(dsobj)}")
        if dsobj.description:
            builder.append(
                replace_description(dsobj.description, self._replace_description)
            )
        for dobj, dsobj in self.iter_documentation_attrs():
            if (
                isinstance(dobj, Variable)
                and not dsobj.description
                and not dobj.type_annotation
            ):
                continue
            if isinstance(dobj, Class) and hasattr(dobj.obj, "__members__"):
                builder.append(self.render_Enum(dobj, dsobj))
                continue
            builder.append(
                getattr(self, "render_" + dobj.__class__.__name__)(dobj, dsobj)
            )
        return "\n\n".join(builder)

    def add_link(self, dobj: Doc, *, repr_text: str = None) -> str:
        filepath = self.uri_factory(dobj.module.refname, dobj.module.is_package).split(
            os.sep
        )
        current_filepath = self.current_filepath.split(os.sep)
        relatived_path: List[str] = []
        if not filepath == current_filepath:
            while filepath and current_filepath and filepath[0] == current_filepath[0]:
                filepath.pop(0)
                current_filepath.pop(0)
            for _ in range(len(current_filepath) - 1):
                relatived_path.append("..")
            if not relatived_path:
                relatived_path.append(".")
            relatived_path.extend(filepath)
        return "[{}]({}#{})".format(
            repr_text or dobj.qualname,
            "/".join(relatived_path),
            self.slugify(get_title(dobj)) if self.slugify else dobj.heading_id,
        )

    def _replace_description(self, match: re.Match) -> str:
        name, text, content = match.groups()
        if name == "version":
            return get_version(content, prefix="")
        elif name == "ref":
            dobj = self.dmodule.context.get(content)
            if dobj is not None:
                return self.add_link(dobj, repr_text=text)
        return match.group()

    @staticmethod
    def indent(s: str, level: int = 1) -> str:
        return _indent(s, prefix=" " * level * 2)

    def render_params(self, section: schema.DocstringSection, level: int = 1) -> str:
        if not section.content:
            return ""
        text = "\n\n".join(
            "- {name}{annotation}{version}{desc}{long_desc}".format(
                name=linkify(
                    p.name.replace("*", r"\*"),
                    add_link=self.add_link,
                    context=self.dmodule.context,
                )
                if section.type is DocstringSection.RETURNS
                else f"`{p.name}`",
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
                desc=f": {replace_description(p.description, self._replace_description)}"
                if p.description
                else "",
                long_desc="\n\n"
                + self.indent(
                    replace_description(p.long_description, self._replace_description)
                )
                if p.long_description
                else "",
            )
            for p in section.content
        )
        return self.indent(text, level)

    def render_Variable(self, dobj: Variable, dsobj: "Docstring") -> str:
        builder: List[str] = []
        ftitle = "## {}{}"
        if dobj.cls is not None:
            ftitle = "#" + ftitle
        builder.append(
            ftitle.format(get_title(dobj), get_version(dsobj))
            + (f" {{#{dobj.heading_id}}}" if not self.slugify else "")
        )
        var_anno = dsobj.var_anno
        if not var_anno:
            for role in dsobj.roles:
                if role.id == "anno":
                    var_anno = role.content
        builder.append(
            f"- **类型:** {var_anno if var_anno else dobj.type_annotation}{get_version(dsobj.type_version.source)}"
        )
        if dsobj.description:
            if "\n" in dsobj.description:
                builder.append("- **说明**")
                builder.append(
                    self.indent(
                        replace_description(
                            dsobj.description, self._replace_description
                        )
                    )
                )
            else:
                builder.append(
                    f"- **说明:** {replace_description(dsobj.description, self._replace_description)}"
                )
        if dsobj.examples:
            section = dsobj.examples
            builder.append("- **用法**")
            builder.append(
                self.indent(
                    replace_description(section.source, self._replace_description)
                )
            )
        return "\n\n".join(builder)

    def render_Function(self, dobj: Function, dsobj: "Docstring") -> str:
        builder: List[str] = []
        overloads: Optional[List[DocstringOverload]] = dsobj.patch.get("overloads")
        ftitle = "## {}{}"
        if dobj.cls is not None:
            ftitle = "#" + ftitle
        builder.append(
            ftitle.format(get_title(dobj), get_version(dsobj))
            + (f" {{#{dobj.heading_id}}}" if not self.slugify else "")
        )
        if dsobj.description:
            builder.append("- **说明**")
            builder.append(
                self.indent(
                    replace_description(dsobj.description, self._replace_description)
                )
            )
        if dsobj.require:
            section = dsobj.require
            builder.append(f"- **要求**{get_version(section)}")
            builder.append(
                self.indent(
                    replace_description(section.source, self._replace_description)
                )
            )
        if overloads:
            builder.append("- **重载**")
            for i, overload in enumerate(overloads):
                builder.append(self.indent(f"**{i + 1}.** `{overload.signature}`"))
                builder.append(self.indent("- **参数**"))
                builder.append(self.render_params(overload.args, 2))
                builder.append(self.indent("- **返回**"))
                builder.append(self.render_params(overload.returns, 2))
        else:
            if dsobj.args.content:
                builder.append(f"- **参数**{get_version(dsobj.args)}")
                builder.append(self.render_params(dsobj.args))
            builder.append(f"- **返回**{get_version(dsobj.returns)}")
            builder.append(self.render_params(dsobj.returns))
        if dsobj.raises:
            section = dsobj.raises
            builder.append(f"- **异常**{get_version(section)}")
            builder.append(
                self.render_params(section)
                or self.indent(
                    replace_description(section.source, self._replace_description)
                )
            )
        if dsobj.examples:
            section = dsobj.examples
            builder.append("- **用法**")
            builder.append(
                self.indent(
                    replace_description(section.source, self._replace_description)
                )
            )
        if dsobj.attributes:
            section = dsobj.attributes
            builder.append("- **属性**")
            builder.append(self.render_params(section))
        return "\n\n".join(builder)

    def render_Enum(self, dobj: Class, dsobj: "Docstring") -> str:
        builder: List[str] = []
        builder.append(
            "## {}{}".format(get_title(dobj), get_version(dsobj))
            + (f" {{#{dobj.heading_id}}}" if not self.slugify else "")
        )
        if dsobj.description:
            builder.append("- **说明**")
            builder.append(
                self.indent(
                    replace_description(dsobj.description, self._replace_description)
                )
            )
        members = getattr(dobj.obj, "__members__")
        if members:
            builder.append("- **枚举成员**")
            builder.append(
                self.indent(
                    "\n\n".join(
                        "- `{}`{}".format(
                            name,
                            f": {replace_description(dobj.var_comments[name], self._replace_description)}"
                            if name in dobj.var_comments
                            else "",
                        )
                        for name in members.keys()
                    )
                )
            )
        return "\n\n".join(builder)

    def render_Class(self, dobj: Class, dsobj: "Docstring") -> str:
        builder: List[str] = []
        builder.append(
            "## {}{}".format(get_title(dobj), get_version(dsobj))
            + (f" {{#{dobj.heading_id}}}" if not self.slugify else "")
        )
        if dsobj.description:
            builder.append("- **说明**")
            builder.append(
                self.indent(
                    replace_description(dsobj.description, self._replace_description)
                )
            )
        if dsobj.require:
            section = dsobj.require
            builder.append(f"- **要求**{get_version(section)}")
            builder.append(
                self.indent(
                    replace_description(section.source, self._replace_description)
                )
            )
        if dsobj.args:
            section = dsobj.args
            if section.content:
                builder.append(f"- **参数**{get_version(section)}")
                builder.append(self.render_params(section))
        if dsobj.examples:
            section = dsobj.examples
            builder.append("- **用法**")
            builder.append(
                self.indent(
                    replace_description(section.source, self._replace_description)
                )
            )
        if dsobj.attributes:
            section = dsobj.attributes
            for dp in section.content:
                builder.append(f"### _other-attr_ `{dp.name}`")
                if dp.description:
                    builder.append(
                        replace_description(dp.description, self._replace_description)
                    )
                if dp.long_description:
                    builder.append(
                        replace_description(
                            dp.long_description, self._replace_description
                        )
                    )
        return "\n\n".join(builder)

    def render_LibraryAttr(self, dobj: LibraryAttr, dsobj: "Docstring") -> str:
        builder: List[str] = []
        builder.append(f"## {get_title(dobj)}")
        builder.append(dobj.docstring if dobj.docstring else "暂无文档")
        return "\n\n".join(builder)
