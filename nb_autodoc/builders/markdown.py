import inspect
from contextlib import contextmanager
from functools import singledispatch
from textwrap import indent
from typing import Callable, Dict, Generator, Optional, Union
from typing_extensions import Literal

from nb_autodoc import nodes
from nb_autodoc.builders import Builder, MemberIterator
from nb_autodoc.config import Config
from nb_autodoc.manager import (
    Class,
    EnumMember,
    Function,
    LibraryAttr,
    Module,
    ModuleManager,
    Variable,
)
from nb_autodoc.typing import T_Definition
from nb_autodoc.utils import isenumclass, stringify_signature

from .helpers import vuepress_slugify


def _find_kind_from_roles(roles: list[nodes.Role]) -> Optional[str]:
    for role in roles:
        if role.name == "kind":
            return role.content


def _find_ver_from_roles(roles: list[nodes.Role]) -> Optional[str]:
    for role in roles:
        if role.name == "ver" or role.name == "version":
            return role.content


def get_version_badge(ver: str) -> str:
    if ver.endswith("-"):
        return f'<Badge text="{ver}" type="error"/>'
    else:
        return f'<Badge text="{ver}"/>'


@singledispatch
def get_bare_title(dobj: T_Definition) -> Optional[str]:
    """Returns None if not implementation found for object."""
    return None


@get_bare_title.register
def get_class_title(dobj: Class) -> str:
    kind = _find_kind_from_roles(dobj.doctree.roles) if dobj.doctree else None
    if kind is None:
        if isenumclass(dobj.pyobj):
            kind = "enum"
        elif inspect.isabstract(dobj.pyobj):
            kind = "abstract class"
        else:
            kind = "class"
    body = dobj.name
    if not isenumclass(dobj.pyobj):
        if dobj.signature:
            body += stringify_signature(dobj.signature)
        else:
            body += "(<auto>)"
    return f"_{kind}_ `{body}`"


@get_bare_title.register
def get_function_title(dobj: Function) -> str:
    kind = _find_kind_from_roles(dobj.doctree.roles) if dobj.doctree else None
    if kind is None:
        builder = []
        if getattr(dobj.pyobj, "__isabstractmethod__", False):
            builder.append("abstract")
        if inspect.iscoroutinefunction(dobj.pyobj):
            builder.append("async")
        if dobj.cls:
            if isinstance(dobj.pyobj, classmethod):
                builder.append("classmethod")
            elif isinstance(dobj.pyobj, staticmethod):
                builder.append("staticmethod")
            else:
                builder.append("method")
        else:
            builder.append("def")
        kind = " ".join(builder)
    body = dobj.name
    if dobj.signature:
        body += stringify_signature(dobj.signature)
    else:
        body += "(<auto>)"
    return f"_{kind}_ `{body}`"


@get_bare_title.register
def get_variable_title(dobj: Variable) -> str:
    kind = _find_kind_from_roles(dobj.doctree.roles) if dobj.doctree else None
    if kind is None:
        if isinstance(dobj.pyobj, property):
            if getattr(dobj.pyobj, "__isabstractmethod__", False):
                kind = "abstract property"
            else:
                kind = "property"
        elif dobj.cls:
            kind = "instance-var" if dobj.is_instvar else "class-var"
        else:
            kind = "var"
    body = dobj.name
    return f"_{kind}_ `{body}`"


@get_bare_title.register
def get_libraryattr_title(dobj: LibraryAttr) -> str:
    return f"_library-attr_ `{dobj.name}`"


# TODO: i18n
class Renderer:
    def __init__(
        self, itor: MemberIterator, *, add_heading_id: bool, config: Config
    ) -> None:
        self.member_iterator = itor
        self.add_heading_id = add_heading_id
        self.indent_size = config["markdown_indent_size"]
        self._builder: list[str] = []
        self._indent: int = 0
        self._level: int = 1

    def write(self, s: str) -> None:
        self._builder.append(s)

    @contextmanager
    def block(self) -> Generator[None, None, None]:
        self._indent += self.indent_size
        yield
        self._indent -= self.indent_size

    @contextmanager
    def heading(self) -> Generator[None, None, None]:
        self._level += 1
        yield
        self._level -= 1

    @contextmanager
    def delimit(self, start: str, end: str) -> Generator[None, None, None]:
        self.write(start)
        yield
        self.write(end)

    def fill(self, s: str) -> None:
        if self._indent:
            self.write(indent(s, " " * self._indent))
        else:
            self.write(s)

    def newline(self, s: str = "") -> None:
        self.write("\n\n")
        if s:
            self.fill(s)

    def title(self, dobj: T_Definition) -> None:
        version = None
        if dobj.doctree:
            version = _find_ver_from_roles(dobj.doctree.roles)
            if not version:
                # find version in `Version:` InlineValue section
                for section in dobj.doctree.sections:
                    if (
                        isinstance(section, nodes.InlineValue)
                        and section.type == "version"
                    ):
                        version = section.value
                        break
        body = get_bare_title(dobj)
        if body is None:
            raise RuntimeError(
                f"cannot create title for {type(dobj)}, maybe it is unlinkable"
            )
        self.write(f"{'#' * self._level} {body}")
        if version:
            self.write(" ")
            self.write(get_version_badge(version))
        if self.add_heading_id:
            self.write(f" {{#{heading_id_slugify_impl(dobj)}}}")

    def visit(self, dobj: Union[T_Definition, nodes.section]) -> None:
        visitor = getattr(self, "visit_" + dobj.__class__.__name__, None)
        if visitor:
            visitor(dobj)
        else:
            raise RuntimeError(f"unexpected type {dobj.__class__}")

    def render(self, dobj: Module, end: str = "\n") -> str:
        self._builder = []
        self.visit_Module(dobj)
        self._builder.append(end)
        return "".join(self._builder)

    def visit_Module(self, dobj: Module) -> None:
        frontmatter = None
        if dobj.doctree:
            for section in dobj.doctree.sections:
                if isinstance(section, nodes.FrontMatter):
                    frontmatter = section
                    break
        if frontmatter:
            self.write("---\n")
            self.write(frontmatter.value)
            self.write("\n---\n\n")
        self.write(f"# {dobj.name}")
        self.current_module = dobj
        if dobj.doctree:
            self.newline()
            self.visit_Docstring(dobj.doctree, is_module=True)
        with self.heading():
            for member in self.member_iterator.iter_module(dobj):
                self.newline()
                self.visit(member)

    def visit_LibraryAttr(self, dobj: LibraryAttr) -> None:
        self.title(dobj)
        self.newline()
        self.visit_Docstring(dobj.doctree)

    def visit_Variable(self, dobj: Variable) -> None:
        self.title(dobj)
        self.newline("- **类型:**")
        if dobj.annotation:
            self.write(" ")
            self.write(repr(dobj.annotation.ann))
        typeversion = None
        if dobj.doctree:
            for section in dobj.doctree.sections:
                if (
                    isinstance(section, nodes.InlineValue)
                    and section.type == "typeversion"
                ):
                    typeversion = section.value
                    break
        if typeversion:
            self.write(" ")
            self.write(get_version_badge(typeversion))
        if dobj.doctree:
            self.newline()
            self.visit_Docstring(dobj.doctree)

    def visit_Function(self, dobj: Function) -> None:
        self.title(dobj)
        if dobj.doctree:
            self.newline()
            self.visit_Docstring(dobj.doctree)

    def visit_Class(self, dobj: Class) -> None:
        self.title(dobj)
        if dobj.doctree:
            self.newline()
            self.visit_Docstring(dobj.doctree)
        ctx = self.block() if isenumclass(dobj.pyobj) else self.heading()
        with ctx:
            for member in self.member_iterator.iter_class(dobj):
                self.newline()
                self.visit(member)

    def visit_EnumMember(self, dobj: EnumMember) -> None:
        self.fill(f"- `{dobj.name}: {dobj.value!r}`")

    # docstring renderer
    def visit_Docstring(self, dsobj: nodes.Docstring, is_module: bool = False) -> None:
        if is_module:
            if dsobj.descr:
                self.write(dsobj.descr)
            if dsobj.long_descr:
                self.newline(dsobj.long_descr)
        elif dsobj.long_descr:
            self.fill("- **说明**")
            with self.block():
                self.newline(dsobj.descr)
                self.newline(dsobj.long_descr)
        elif dsobj.descr:
            self.fill("- **说明:** ")
            self.write(dsobj.descr)
        # skip two special section
        # TODO: fix it
        for member in filter(
            lambda x: not isinstance(x, (nodes.InlineValue, nodes.FrontMatter)),
            dsobj.sections,
        ):
            self.newline()
            self.visit(member)

    def visit_ColonArg(
        self, dsobj: nodes.ColonArg, isvar: bool = False, iskw: bool = False
    ) -> None:
        self.fill("- ")
        if dsobj.name:
            with self.delimit("`", "`"):
                if isvar:
                    self.write("*")
                if iskw:
                    self.write("**")
                self.write(dsobj.name)
            if dsobj.annotation:
                with self.delimit("(", ")"):
                    self.write(dsobj.annotation)
        elif dsobj.annotation:
            self.write(dsobj.annotation)
        else:
            raise RuntimeError("ColonArg requires at least name or annotation field")
        if dsobj.descr:
            self.write(": ")
            self.write(dsobj.descr)
        if dsobj.long_descr:
            with self.block():
                self.newline(dsobj.long_descr)

    # sections
    def visit_Text(self, dsobj: nodes.Text) -> None:
        self.write(dsobj.value)

    def visit_Args(self, dsobj: nodes.Args) -> None:
        self.fill(f"- **{dsobj.name}**")
        with self.block():
            for arg in dsobj.args:
                self.newline()
                self.visit_ColonArg(arg)
            if dsobj.vararg:
                self.newline()
                self.visit_ColonArg(dsobj.vararg, isvar=True)
            for arg in dsobj.kwonlyargs:
                self.newline()
                self.visit_ColonArg(arg)
            if dsobj.kwarg:
                self.newline()
                self.visit_ColonArg(dsobj.kwarg, iskw=True)

    def visit_Attributes(self, dsobj: nodes.Attributes) -> None:
        self.fill(f"- **{dsobj.name}**")
        with self.block():
            for arg in dsobj.args:
                self.newline()
                self.visit_ColonArg(arg)

    def visit_Examples(self, dsobj: nodes.Examples) -> None:
        self.fill(f"- **{dsobj.name}**")
        with self.block():
            self.newline(dsobj.value)

    def visit_Raises(self, dsobj: nodes.Raises) -> None:
        self.fill(f"- **{dsobj.name}**")
        with self.block():
            for arg in dsobj.args:
                self.newline()
                self.visit_ColonArg(arg)

    def _visit_return_like(self, dsobj: Union[nodes.Returns, nodes.Yields]) -> None:
        self.fill(f"- **{dsobj.name}**")
        if dsobj.version:
            self.write(" ")
            self.write(get_version_badge(dsobj.version))
        with self.block():
            if isinstance(dsobj.value, str):
                self.newline(dsobj.value)
            else:
                self.newline()
                self.visit_ColonArg(dsobj.value)

    visit_Returns = visit_Yields = _visit_return_like

    def visit_Require(self, dsobj: nodes.Require) -> None:
        self.fill(f"- **{dsobj.name}**")
        if dsobj.version:
            self.write(" ")
            self.write(get_version_badge(dsobj.version))
        with self.block():
            self.newline(dsobj.value)


def heading_id_slugify_impl(dobj: T_Definition) -> str:
    # EnumMember is unlinkable and expect None, but we skipped
    return dobj.qualname.replace(".", "-")
    # return dobj.qualname  # docusauras cannot recognize "."


def vuepress_slugify_impl(dobj: T_Definition) -> Optional[str]:
    title = get_bare_title(dobj)
    if title is None:
        return None
    return vuepress_slugify(title)


# impl return the slug of linkable object
_slugify_impls: Dict[str, Callable[[T_Definition], Optional[str]]] = {
    "heading_id": heading_id_slugify_impl,
    "vuepress": vuepress_slugify_impl,
}


class MarkdownBuilder(Builder):
    def __init__(
        self,
        manager: ModuleManager,
        *,
        link_mode: Literal["heading_id", "vuepress"] = "heading_id",
    ) -> None:
        self.link_mode = link_mode
        super().__init__(manager)

    def get_suffix(self) -> str:
        return ".md"

    def get_slugify_impl(self) -> Callable[[T_Definition], Optional[str]]:
        return _slugify_impls[self.link_mode]

    def text(self, module: Module) -> str:
        renderer = Renderer(
            self.get_member_iterator(module),
            add_heading_id=self.link_mode == "heading_id",
            config=self.manager.config,
        )
        return renderer.render(module)

    # replace ref
    # ref: r"{(?P<name>\w+?)}`(?:(?P<text>[^{}]+?) <)?(?P<content>[\w\.]+)(?(text)>)`"
