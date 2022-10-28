import ast
from typing import Type


class NodeVisitorX:
    def visit(self, node: ast.AST) -> None:
        visitor = getattr(self, "visit_" + node.__class__.__name__, None)
        if visitor is not None:
            visitor(node)


def super_visit(cls_: Type[object], self_: object, node: ast.AST) -> None:
    """Call super visitor if exists."""
    visitor = getattr(super(cls_, self_), "visit_" + node.__class__.__name__, None)
    if visitor is not None:
        visitor(node)
