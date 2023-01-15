from contextlib import contextmanager
from typing import Dict, Generator, NamedTuple, Union

from nb_autodoc.builders import Builder, MemberIterator
from nb_autodoc.manager import (
    Class,
    EnumMember,
    Function,
    LibraryAttr,
    Module,
    Variable,
)
from nb_autodoc.typing import T_Definition


class Context(NamedTuple):
    doc_location: Dict[str, str]
    """Object documentation locator. Dict key is refname, value is anchor."""


class Renderer:
    def __init__(self, itor: MemberIterator) -> None:
        self.member_iterator = itor
        self._builder: list[str] = []
        self._indent: int = 0
        self._title_cached: bool = False

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


class MarkdownBuilder(Builder):
    def get_suffix(self) -> str:
        return ".md"

    def text(self, module: Module) -> str:
        renderer = Renderer(self.get_member_iterator(module))
        return renderer.render(module)

    # replace ref
    # ref: r"{(?P<name>\w+?)}`(?:(?P<text>[^{}]+?) <)?(?P<content>[\w\.]+)(?(text)>)`"
