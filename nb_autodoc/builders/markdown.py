from typing import Callable, Dict, Iterable, NamedTuple, TypeVar, Union

from nb_autodoc.builders import Builder, MemberIterator
from nb_autodoc.manager import (
    Class,
    EnumMember,
    Function,
    LibraryAttr,
    Module,
    Variable,
    WeakReference,
)
from nb_autodoc.typing import T_DefinitionOrRef

T = TypeVar("T")


class Context(NamedTuple):
    doc_location: Dict[str, str]
    """Object documentation locator. Dict key is refname, value is anchor."""


def interleave(
    inter: Callable[[], None], f: Callable[[T], None], seq: Iterable[T]
) -> None:
    """Call f on each item in seq, calling inter() in between."""
    seq = iter(seq)
    try:
        f(next(seq))
    except StopIteration:
        pass
    else:
        for x in seq:
            inter()
            f(x)


class Renderer:
    def __init__(self, itor: MemberIterator) -> None:
        self.member_iterator = itor
        self.builder: list[str] = []

    def write(self, s: str) -> None:
        self.builder.append(s)

    def delimit_write_between(
        self, seq: Iterable[T_DefinitionOrRef], delimiter: str
    ) -> None:
        interleave(lambda: self.write(delimiter), self.visit, seq)

    def visit(self, dobj: Union[T_DefinitionOrRef, Module]) -> None:
        visitor = getattr(self, "visit_" + dobj.__class__.__name__, None)
        if visitor:
            visitor(dobj)
        else:
            raise RuntimeError(f"unexpected type {dobj.__class__}")

    def render(
        self, dobj: Union[T_DefinitionOrRef, Module], append_newline: bool = True
    ) -> str:
        self.builder = []
        self.visit(dobj)
        if append_newline:
            self.builder.append("\n")
        return "".join(self.builder)

    def visit_Module(self, module: Module) -> None:
        # write dobj.doc
        self.write(f"# {module.name}\n\n")
        self.delimit_write_between(self.member_iterator.iter_module(module), "\n\n")

    def visit_WeakReference(self, ref: WeakReference) -> None:
        self.write(f"## _ref_ `{ref.name}`")

    def visit_LibraryAttr(self, libattr: LibraryAttr) -> None:
        self.write(f"## _lib_ `{libattr.name}`")

    def visit_Variable(self, var: Variable) -> None:
        if var.cls:
            self.write(f"### _var_ `{var.name}`")
        else:
            self.write(f"## _var_ `{var.name}`")

    def visit_Function(self, func: Function) -> None:
        if func.cls:
            self.write(f"### _func_ `{func.name}`")
        else:
            self.write(f"## _func_ `{func.name}`")

    def visit_Class(self, cls: Class) -> None:
        self.write(f"## _class_ `{cls.name}`\n\n")
        self.delimit_write_between(self.member_iterator.iter_class(cls), "\n\n")

    def visit_EnumMember(self, enumm: EnumMember) -> None:
        self.write(f"- `{enumm.name}: {enumm.value!r}`")


class MarkdownBuilder(Builder):
    def get_suffix(self) -> str:
        return ".md"

    def text(self, module: Module) -> str:
        return Renderer(MemberIterator(module)).render(module)

    # replace ref
    # ref: r"{(?P<name>\w+?)}`(?:(?P<text>[^{}]+?) <)?(?P<content>[\w\.]+)(?(text)>)`"
