"""Python Code Analyzer by parsing and analyzing AST.
"""


import ast
import sys
from contextlib import contextmanager
from typing import Any, Callable, Generator, Iterable, List, TypeVar

T = TypeVar("T")


class Analyzer:
    def __init__(self, code: str) -> None:
        ...


# Though python compat node in previous version
# It's not good to fixup and return correct node
def is_constant_node(node: ast.AST) -> bool:
    if sys.version_info >= (3, 8):
        return isinstance(node, ast.Constant)
    return isinstance(
        node, (ast.Num, ast.Str, ast.Bytes, ast.NameConstant, ast.Ellipsis)
    )


def get_constant_value(node: ast.AST) -> Any:
    if sys.version_info < (3, 8) and isinstance(node, ast.Ellipsis):
        return ...
    return getattr(node, node._fields[0])


def interleave(
    inter: Callable[[], None], f: Callable[[T], None], seq: Iterable[T]
) -> None:
    """Call f on each item on seq, calling inter() in between."""
    seq = iter(seq)
    try:
        f(next(seq))
    except StopIteration:
        pass
    else:
        for x in seq:
            inter()
            f(x)


class _Unparser(ast.NodeVisitor):
    """Utilities like `ast._Unparser` in `python>=3.9`.

    Subclassing this class and implement the unparse method.
    """

    def __init__(self) -> None:
        self._source: List[str] = []

    def traverse(self, node: ast.AST) -> None:
        """Alternative call for `super().visit()` since `visit` is overridden.

        Unlike ast._Unparser.traverse, this do not accept list argument for concision.
        """
        super().visit(node)

    def visit(self, node: ast.AST) -> str:
        self._source = []
        self.traverse(node)
        return "".join(self._source)

    def write(self, s: str) -> None:
        self._source.append(s)

    @contextmanager
    def delimit(self, start: str, end: str) -> Generator[None, None, None]:
        self.write(start)
        yield
        self.write(end)


def convert_annot(s: str) -> str:
    return AnnotUnparser().visit(ast.parse(s, mode="eval").body)


class AnnotUnparser(_Unparser):
    """Special unparser for annotation with py3.9+ new style.

    Legal annotation consists of (ast.Name, ast.Attribute, ast.Subscript, ellipsis).
    `...` is only allowed in `ast.Subscript`, like Callable and Tuple.

    Annotation node should be transformed first to avoid naming problem like `T.Union`.

    In 3.9+ new style:
        Union can be written in `X | Y` and Optional alias  `X | None` (PEP 604)
        Standard container type that allows subscript: list, set, tuple, dict (PEP 585)
        Callable alias `(X, Y) -> None` (PEP 484)
    """

    def visit(self, node: ast.AST) -> str:
        if is_constant_node(node):
            value = get_constant_value(node)
            if not isinstance(value, str):
                raise ValueError(f"value {value!r} is invalid in annotation")
            return value
        return super().visit(node)

    def traverse(self, node: ast.AST) -> None:
        """Ensure traversing the valid visitor."""
        if is_constant_node(node):
            value = get_constant_value(node)
            if value is ...:
                self.write("...")
            elif isinstance(value, str):
                self.write(repr(str))
            elif value is None:
                self.write("None")
            else:
                raise ValueError(
                    "only str and ... constant is allowed in subscript scope, "
                    f"got {value.__class__}"
                )
            return
        if node.__class__.__name__ not in ("Name", "Attribute", "Subscript"):
            raise ValueError(f"invalid annotation node type {node.__class__.__name__}")
        return super().traverse(node)

    def visit_Name(self, node: ast.Name) -> None:
        self.write(node.id)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.traverse(node.value)
        self.write(".")
        self.write(node.attr)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if not isinstance(node.value, ast.Name):
            self.visit_Subscript_orig(node)
            return
        name = node.value
        slice_spec: Any  # Name, Tuple, etc.
        if sys.version_info < (3, 9):
            if isinstance(node.slice, ast.Index):
                slice_spec = node.slice.value
            else:
                self.visit_Subscript_orig(node)
                return
        else:
            slice_spec = node.slice
        if name.id in ("List", "Set", "Tuple", "Dict"):
            self.write(name.id.lower())
            with self.delimit("[", "]"):
                if isinstance(slice_spec, ast.Tuple):
                    interleave(lambda: self.write(", "), self.traverse, slice_spec.elts)
                else:
                    self.traverse(slice_spec)
        elif name.id == "Union":
            interleave(lambda: self.write(" | "), self.traverse, slice_spec.elts)
        elif name.id == "Optional":
            self.traverse(slice_spec)
            self.write(" | None")
        elif name.id == "Callable":
            params = slice_spec.elts[0]
            if is_constant_node(params) and get_constant_value(params) is ...:
                self.write("(*Any, **Any)")
            else:  # must be ast.List
                with self.delimit("(", ")"):
                    interleave(lambda: self.write(", "), self.traverse, params.elts)
            self.write(" -> ")
            return_t = slice_spec.elts[1]
            if (
                isinstance(return_t, ast.Subscript)
                and isinstance(return_t.value, ast.Name)
                and (return_t.value.id == "Union" or return_t.value.id == "Optional")
            ):
                # Avoid ambitious return union, details in bpo-43609
                # Thanks https://gist.github.com/cleoold/6db17392b33de59c10303c6337eb692f
                with self.delimit("(", ")"):
                    self.traverse(return_t)
            else:
                self.traverse(return_t)

    def visit_Subscript_orig(self, node: ast.Subscript) -> Any:
        self.traverse(node.value)
        with self.delimit("[", "]"):
            if sys.version_info < (3, 9):
                if isinstance(node.slice, ast.Index):
                    self.traverse(node.slice.value)
                else:
                    self.traverse(node.slice)  # block
            elif isinstance(node.slice, ast.Tuple):
                interleave(lambda: self.write(", "), self.traverse, node.slice.elts)
            else:
                self.traverse(node.slice)
