import ast
import itertools
import sys
from typing import Dict, List, Optional

from nb_autodoc.utils import resolve_name

from .utils import (
    get_assign_targets,
    get_constant_value,
    get_target_names,
    is_constant_node,
)

_DEF_VISIT = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.ImportFrom)


class DefinitionFinder:
    """Find all binding names, variable comments, type comments and annotations.

    The following constructs bind names:

        - class or function definition
        - assignment expression (:=)
        - targets that create new variable
        - import statement
        - compound statement body (if, while, for, try, with, match)

    A name can refer to:

        - definition
        - external
        - library attr

    Before nb_autodoc v0.2.0, `#:` special comment syntax is allowed.
    See: https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html
    Now it is deprecated for implicit meaning and irregular syntax.

    If assign has multiple target like `a, b = 1, 2`, its docstring and type comment
    will be assigned to each name.

    Instance var in `A.__init__` saves in `A.__init__.a` format.
    """

    def __init__(self, name: str, package: Optional[str]) -> None:
        # arg should all be optional (as analysis feature)
        self.name = name
        """Module name to determind external."""
        self.package = package
        """Package name."""
        self.ctx: List[str] = []
        self.previous: Optional[ast.AST] = None
        self.current_class: List[str] = []
        self.current_function: Optional[ast.FunctionDef] = None
        self.counter = itertools.count()
        self.binding_names: Dict[str, int] = {}
        self.definitions: Dict[str, int] = {}
        """Definition entry."""
        self.externals: Dict[str, str] = {}
        """External reference."""
        self.var_comments: Dict[str, str] = {}
        """Variable comment."""
        self.annotations: Dict[str, ast.Expression] = {}
        self.type_comments: Dict[str, ast.Expression] = {}
        # special import namespace context
        self.imp_typing: List[str] = []
        self.imp_typing_overload: List[str] = []

    def get_qualname_for(self, name: str) -> str:
        if not self.ctx:
            return name
        return ".".join(self.ctx) + "." + name

    def get_self(self) -> str:
        """Return the first argument name in a method if exists."""
        if self.current_class and self.current_function:
            if sys.version_info >= (3, 8) and self.current_function.args.posonlyargs:
                return self.current_function.args.posonlyargs[0].arg
            if self.current_function.args.args:
                return self.current_function.args.args[0].arg
        return ""

    def add_definition_entry(self, name: str) -> None:
        qualname = self.get_qualname_for(name)
        self.definitions[qualname] = next(self.counter)

    def add_comment(self, name: str, comment: str) -> None:
        qualname = self.get_qualname_for(name)
        self.var_comments[qualname] = comment

    def add_annotation(self, name: str, annotation: ast.expr) -> None:
        qualname = self.get_qualname_for(name)
        self.annotations[qualname] = ast.Expression(annotation)

    def add_type_comment(self, name: str, type_comment: str) -> None:
        qualname = self.get_qualname_for(name)
        expre = ast.parse(repr(type_comment), mode="eval")
        self.type_comments[qualname] = expre

    def traverse_body(self, stmts: List[ast.stmt]) -> None:
        """Traverse visit Def body.

        Add definition and pick comment for all Assign or AnnAssign.
        Distribute if the node is another Def.
        """
        for i, stmt in enumerate(stmts):
            if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                targets = get_assign_targets(stmt)
                names = tuple(
                    itertools.chain.from_iterable(
                        get_target_names(i, self.get_self()) for i in targets
                    )
                )
                if not names:
                    continue
                for name in names:
                    self.add_definition_entry(name)
                # Add annotation for AnnAssign or type_comment for Assign
                if isinstance(stmt, ast.AnnAssign):
                    self.add_annotation(names[0], stmt.annotation)
                else:
                    type_comment = getattr(stmt, "type_comment", None)
                    if type_comment:
                        for name in names:
                            self.add_type_comment(name, type_comment)
                if i == len(stmts) - 1:
                    continue
                after_stmt = stmts[i + 1]
                # Add comments if exists
                if isinstance(after_stmt, ast.Expr) and is_constant_node(
                    after_stmt.value
                ):
                    comment = get_constant_value(after_stmt.value)
                    if isinstance(comment, str):
                        for name in names:
                            self.add_comment(name, comment)
            elif isinstance(stmt, _DEF_VISIT):
                self.visit(stmt)

    def visit(self, node: ast.AST) -> None:
        """Visit a concrete node."""
        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        visitor(node)

    def generic_visit(self, node: ast.AST) -> None:
        """Disallow generic visit."""

    def visit_Module(self, node: ast.Module) -> None:
        self.traverse_body(node.body)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        absoluate_module = resolve_name(node, self.package)
        if absoluate_module == self.name or absoluate_module.startswith(
            self.name + "."
        ):
            for alias in node.names:
                varname = alias.asname or alias.name
                self.add_definition_entry(varname)
                self.externals[varname] = absoluate_module + "." + alias.name

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if len(self.current_class) == 0:
            self.add_definition_entry(node.name)
            self.current_class.append(node.name)
            self.ctx.append(node.name)
            self.traverse_body(node.body)
            self.ctx.pop()
            self.current_class.pop()
        elif len(self.current_class) == 1:
            self.add_definition_entry(node.name)
        else:
            pass

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if not self.current_function:
            self.add_definition_entry(node.name)
            self.current_function = node
            self.ctx.append(node.name)
            if self.current_class and node.name == "__init__":
                self.traverse_body(node.body)
            self.ctx.pop()
            self.current_function = None

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return self.visit_FunctionDef(node)  # type: ignore
