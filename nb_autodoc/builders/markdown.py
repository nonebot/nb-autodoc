from contextlib import contextmanager
from functools import singledispatch
from typing import Callable, Dict, Generator, Optional, Union
from typing_extensions import Literal

from nb_autodoc.builders import Builder, MemberIterator
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
from nb_autodoc.utils import isenumclass

from .helpers import vuepress_slugify


@singledispatch
def get_bare_title(dobj: T_Definition) -> Optional[str]:
    """Returns None if not implementation found for object."""
    return None


@get_bare_title.register
def get_class_title(dobj: Class) -> str:
    ...


@get_bare_title.register
def get_function_title(dobj: Function) -> str:
    ...


@get_bare_title.register
def get_variable_title(dobj: Variable) -> str:
    ...


@get_bare_title.register
def get_libraryattr_title(dobj: LibraryAttr) -> str:
    ...


class Renderer:
    def __init__(self, itor: MemberIterator) -> None:
        self.member_iterator = itor
        self._builder: list[str] = []
        self._indent: int = 0

    def write(self, s: str) -> None:
        self._builder.append(s)

    @contextmanager
    def block(self) -> Generator[None, None, None]:
        self._indent += 1
        yield
        self._indent -= 1

    def start_newline(self, s: str) -> None:
        self.write("\n\n")
        self.write(s)

    def visit(self, dobj: Union[T_Definition, Module]) -> None:
        visitor = getattr(self, "visit_" + dobj.__class__.__name__, None)
        if visitor:
            visitor(dobj)
        else:
            raise RuntimeError(f"unexpected type {dobj.__class__}")

    def render(self, dobj: Module, end: str = "\n") -> str:
        self._builder = []
        self.visit(dobj)
        self._builder.append(end)
        return "".join(self._builder)

    def get_title(
        self, dobj: Union[T_Definition, Module], *, version: Optional[str] = None
    ) -> str:
        ...

    def visit_Module(self, module: Module) -> None:
        self.write(f"# {module.name}\n\n")
        self.write("module docstring")
        self.current_module = module
        for dobj in self.member_iterator.iter_module(module):
            self.visit(dobj)

    def visit_LibraryAttr(self, libattr: LibraryAttr) -> None:
        self.write(f"## _library-attr_ `{libattr.name}`")
        self.start_newline(libattr.doc)

    def visit_Variable(self, var: Variable) -> None:
        if var.cls:
            self.write("#")
        self.write(f"## _var_ `{var.name}`")

    def visit_Function(self, func: Function) -> None:
        if func.cls:
            self.write("#")
        self.write(f"## _func_ `{func.name}`")

    def visit_Class(self, cls: Class) -> None:
        self.write(f"## _class_ `{cls.name}`\n\n")
        for dobj in self.member_iterator.iter_class(cls):
            self.visit(dobj)

    def visit_EnumMember(self, enumm: EnumMember) -> None:
        self.write(f"- `{enumm.name}: {enumm.value!r}`")


def heading_id_slugify_impl(dobj: T_Definition) -> str:
    # EnumMember is unlinkable and expect None, but we skipped
    return dobj.qualname.replace(".", "-")


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
        renderer = Renderer(self.get_member_iterator(module))
        return renderer.render(module)

    # replace ref
    # ref: r"{(?P<name>\w+?)}`(?:(?P<text>[^{}]+?) <)?(?P<content>[\w\.]+)(?(text)>)`"
