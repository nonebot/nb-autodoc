import ast
import sys
import typing as t

from nb_autodoc.log import logger

from .utils import Unparser, get_constant_value, is_constant_node

T = t.TypeVar("T")


def convert_annot(s: str) -> str:
    """Convert type annotation to new style."""
    try:
        node = ast.parse(s, mode="eval").body
    except SyntaxError:  # probably already new style
        return s
    return NewAnnotUnparser().visit(node)


class NewAnnotUnparser(Unparser):
    """Special unparser for annotation with py3.9+ new style.

    Legal annotation consists of (ast.Name, ast.Attribute, ast.Subscript).
    `...` is only allowed in `ast.Subscript`, like Callable and Tuple.
    str and None is OK.

    Annotation node should be transformed first to avoid naming problem like `T.Union`.

    In 3.9+ new style:
        Union can be written in `X | Y` and Optional alias  `X | None` (PEP 604)
        Standard container type that allows subscript: list, set, tuple, dict (PEP 585)
        Callable alias `(X, Y) -> None` (PEP 484)
    """

    def visit(self, node: ast.AST) -> str:
        if not isinstance(node, ast.expr):
            logger.error(
                f"{self.__class__.__name__} expect ast.expr, got {node.__class__}"
            )
            return "<unknown>"
        if is_constant_node(node):
            value = get_constant_value(node)
            if value is None:
                return "None"
            if not isinstance(value, str):
                raise ValueError(f"value {value!r} is invalid in annotation")
            return value
        return super().visit(node)

    def traverse(self, node: ast.expr) -> None:  # type: ignore[override]
        """Ensure traversing the valid visitor."""
        if is_constant_node(node):
            value = get_constant_value(node)
            if value is ...:
                Unparser.write(self, "...")
            elif isinstance(value, str):
                Unparser.write(self, repr(str))
            elif value is None:
                Unparser.write(self, "None")
            else:
                raise ValueError(
                    "only str, Ellipsis and None is allowed in subscript scope, "
                    f"got {value.__class__}"
                )
            return
        if node.__class__.__name__ not in ("Name", "Attribute", "Subscript"):
            raise ValueError(f"invalid annotation node type {node.__class__.__name__}")
        return super().traverse(node)

    def visit_Name(self, node: ast.Name) -> None:
        Unparser.write(self, node.id)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.traverse(node.value)
        Unparser.write(self, ".")
        Unparser.write(self, node.attr)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if not isinstance(node.value, ast.Name):
            self.visit_Subscript_orig(node)
            return
        name = node.value
        slice_spec: t.Any  # Name, Tuple, etc.
        if sys.version_info < (3, 9):
            if isinstance(node.slice, ast.Index):
                slice_spec = node.slice.value
            else:
                self.visit_Subscript_orig(node)
                return
        else:
            slice_spec = node.slice
        if name.id in ("List", "Set", "Tuple", "Dict"):
            Unparser.write(self, name.id.lower())
            with Unparser.delimit(self, "[", "]"):
                if isinstance(slice_spec, ast.Tuple):
                    Unparser.interleave(
                        lambda: Unparser.write(self, ", "),
                        self.traverse,
                        slice_spec.elts,
                    )
                else:
                    self.traverse(slice_spec)
        elif name.id == "Union":
            Unparser.interleave(
                lambda: Unparser.write(self, " | "), self.traverse, slice_spec.elts
            )
        elif name.id == "Optional":
            self.traverse(slice_spec)
            Unparser.write(self, " | None")
        elif name.id == "Callable":
            params = slice_spec.elts[0]
            if is_constant_node(params) and get_constant_value(params) is ...:
                Unparser.write(self, "(*Any, **Any)")
            else:  # must be ast.List
                with Unparser.delimit(self, "(", ")"):
                    Unparser.interleave(
                        lambda: Unparser.write(self, ", "), self.traverse, params.elts
                    )
            Unparser.write(self, " -> ")
            return_t = slice_spec.elts[1]
            if (
                isinstance(return_t, ast.Subscript)
                and isinstance(return_t.value, ast.Name)
                and (return_t.value.id == "Union" or return_t.value.id == "Optional")
            ):
                # Avoid ambitious return union, details in bpo-43609
                # Thanks https://gist.github.com/cleoold/6db17392b33de59c10303c6337eb692f
                with Unparser.delimit(self, "(", ")"):
                    self.traverse(return_t)
            else:
                self.traverse(return_t)

    def visit_Subscript_orig(self, node: ast.Subscript) -> t.Any:
        self.traverse(node.value)
        with Unparser.delimit(self, "[", "]"):
            if sys.version_info < (3, 9):
                if isinstance(node.slice, ast.Index):
                    self.traverse(node.slice.value)
                else:
                    self.traverse(node.slice)  # block
            elif isinstance(node.slice, ast.Tuple):
                Unparser.interleave(
                    lambda: Unparser.write(self, ", "), self.traverse, node.slice.elts
                )
            else:
                self.traverse(node.slice)
