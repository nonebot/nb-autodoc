"""
Pick variable docstring from module-level and class-level.

Priority: `docstring` > `comment_ahead` > `comment_inline` > `comment_after`

`docstring` is ast.Expr after ast.Assign or ast.AnnAssign.
`comment_ahead` appear in multi-continous lines ahead of assignment.
`comment_inline` appear after assignment.
`comment_after` appear in one line after assignment.

Different from docstring, comment should be marked with `#:`

Example:
    ```python
    #: connect
    #: comment ahead
    a = 1  #: comment inline
    #: comment after
    ```
    a's docstring is 'connect<newline>comment ahead'

    ```python
    #: comment ahead
    a = 1
    '''
    example docstring
    '''
    ```
    a's docstring is 'example docstring'
"""
import re
import ast
import inspect
import itertools
from typing import Iterable, Iterator, List, Dict, Set, Union, Optional, cast


comment_re = re.compile(r"^\s*#: ?(.*)$")
indent_re = re.compile(r"^\s*$")


def extract_all_comments(source: str) -> "VariableCommentPicker":
    picker = VariableCommentPicker(source.splitlines())
    astmodule = ast.parse(source)
    picker.visit(astmodule)
    return picker


def get_assign_targets(node: Union[ast.Assign, ast.AnnAssign]) -> List[ast.expr]:
    """
    An AnnAssign `target` is a single node.
    An Assign `targets` is a list of nodes.

    Example:
        `a = b = 1` return [ast.Name('a'), ast.Name('b')]
        `a, b = c` return [ast.Tuple(('a', 'b'))]
    """
    if isinstance(node, ast.Assign):
        return node.targets
    else:
        return [node.target]


def get_target_names(
    node: Union[str, ast.AST], self: Optional[ast.arg] = None
) -> List[str]:
    """Convert assignment-AST to variable names.
    This raises `TypeError` if the assignment does not create new variable.

    Args:
        node: the `target` in ast.Assign
    """
    if isinstance(node, str):
        return [node]
    node_name = node.__class__.__name__
    if node_name in ("Index", "Num", "Slice", "Str", "Subscript"):
        raise TypeError(f"{node!r} does not create new variable")
    elif node_name == "Name":
        node = cast(ast.Name, node)
        if self is None or node.id == self.arg:
            return [node.id]
        else:
            raise TypeError(f"The assignment {node!r} is not instance variable")
    elif node_name in ("Tuple", "List"):
        node = cast(Union[ast.Tuple, ast.List], node)
        members = []
        for elt in node.elts:
            try:
                members.extend(get_target_names(elt, self))
            except TypeError:
                pass
        return members
    elif node_name == "Attribute":
        node = cast(ast.Attribute, node)
        if (
            node.value.__class__.__name__ == "Name"
            and self
            and cast(ast.Name, node.value).id == self.arg
        ):
            # instance variable
            return [node.attr]
        else:
            raise TypeError(f"The assignment {node!r} is not instance variable")
    else:
        raise NotImplementedError(f"Unexpected node name {node_name!r}")


class VariableCommentPicker(ast.NodeVisitor):
    """
    Python source code parser to pick up variable comments.

    Args:
        buffers: splitlines of source code, visit comment for convenience.
        encoding: encoding to decode bytes in ast.Expr or anyclass from ast.Constant.

    Attribute:
        instance_vars: the instance variable defined in `__init__`
    """

    def __init__(
        self, buffers: Union[Iterable[str], Iterator[str]], encoding: str = "utf-8"
    ) -> None:
        self.buffers = list(buffers)
        self.encoding = encoding
        self.context: List[str] = []
        self.current_class: Optional[ast.ClassDef] = None
        self.current_function: Optional[ast.FunctionDef] = None
        self.comments: Dict[str, str] = {}
        self.instance_vars: Dict[str, Set[str]] = {}
        self.nodoc_classes: Set[str] = set()
        # patch, refactor in v1.0
        self.previous: Optional[ast.AST] = None
        self.visited: List[str] = []
        super().__init__()

    def get_qualname_for(self, name: str) -> Optional[List[str]]:
        if self.current_function:
            if self.current_class:
                return self.context[:-1] + [name]
            else:
                return None
        else:
            return self.context + [name]

    def add_entry(self, name: str) -> None:
        qualname = self.get_qualname_for(name)
        if qualname:
            self.visited.append(".".join(qualname))

    def add_variable_comment(self, name: str, comment: str) -> None:
        qualname = self.get_qualname_for(name)
        if qualname:
            basename = ".".join(qualname[:-1])
            if basename:
                name = ".".join((basename, name))
            self.comments[name] = comment

    def get_self(self) -> Optional[ast.arg]:
        """Returns the name of the first argument if in a function."""
        if self.current_function and self.current_function.args.args:
            return self.current_function.args.args[0]
        else:
            return None

    def get_line(self, lineno: int) -> str:
        """Returns specified line."""
        if lineno - 1 >= len(self.buffers):
            return ""
        return self.buffers[lineno - 1]

    def visit(self, node: ast.AST) -> None:
        """Updates self.previous to the given node."""
        super().visit(node)
        self.previous = node

    def visit_Assign(self, node: Union[ast.Assign, ast.AnnAssign]) -> None:
        """Handles Assign node and pick up a variable comment."""
        # Record if node formed in `self.<instance_var_name>` in `__init__`
        # TODO: add annotations marked in instance assignment
        farg = self.get_self()
        if self.current_class and farg:
            for target in get_assign_targets(node):
                if not isinstance(target, ast.Attribute):
                    continue
                if isinstance(target.value, ast.Name) and target.value.id == farg.arg:
                    self.instance_vars.setdefault(self.current_class.name, set()).add(
                        target.attr
                    )

        try:
            targets = get_assign_targets(node)
            varnames: List[str] = list(
                itertools.chain(
                    *(get_target_names(t, self=self.get_self()) for t in targets)
                )
            )
            current_line = self.get_line(node.lineno)
        except TypeError:
            return  # this assignment is not new definition!

        comment: Optional[str] = None

        if indent_re.match(current_line[: node.col_offset]):
            # TODO: comment col_offset should be the same as node.col_offset

            # check comments before assignment
            comment_lines = []
            for i in range(node.lineno - 1):
                before_line = self.get_line(node.lineno - 1 - i)
                if comment_re.match(before_line):
                    comment_lines.append(comment_re.sub(r"\1", before_line))
                else:
                    break
            if comment_lines:
                comment = "\n".join(reversed(comment_lines))

        if comment is not None:
            for varname in varnames:
                self.add_variable_comment(varname, comment)
            return

        for varname in varnames:
            self.add_entry(varname)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Handles AnnAssign node and pick up a variable comment."""
        self.visit_Assign(node)  # type: ignore

    def visit_Expr(self, node: ast.Expr) -> None:
        """Handles Expr node and pick up a comment if string."""
        if self.current_class and node is self.current_class.body[0]:
            return
        if isinstance(self.previous, (ast.Assign, ast.AnnAssign)) and isinstance(
            node.value, ast.Str
        ):
            try:
                targets = get_assign_targets(self.previous)
                varnames = get_target_names(targets[0], self.get_self())
                for varname in varnames:
                    if isinstance(node.value.s, str):
                        docstring = node.value.s
                    else:
                        docstring = node.value.s.decode(self.encoding)
                    self.add_variable_comment(varname, inspect.cleandoc(docstring))
            except TypeError:
                pass  # this assignment is not new definition!

    def visit_Try(self, node: ast.Try) -> None:
        """Handles Try node and processes body and else-clause.
        This special visitor ignores objects definition in except-clause.
        """
        for subnode in node.body:
            self.visit(subnode)
        for subnode in node.orelse:
            self.visit(subnode)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Handles ClassDef node and set context."""
        # ignore class inner class
        if self.current_class is None:
            first_child = node.body[0]
            if not (
                isinstance(first_child, ast.Expr)
                and isinstance(first_child.value, ast.Str)
            ):
                self.nodoc_classes.add(node.name)
            self.context.append(node.name)
            self.current_class = node
            for child in node.body:
                self.visit(child)
            self.context.pop()
            self.current_class = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Handles FunctionDef node and set context."""
        # ignore function inner function
        if self.current_function is None:
            if not self.current_class or (
                self.current_class and not node.name == "__init__"
            ):
                # only visit __init__ in class
                return
            self.context.append(node.name)
            self.current_function = node
            for child in node.body:
                self.visit(child)
            self.context.pop()
            self.current_function = None

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Handles AsyncFunctionDef node and set context."""
        self.visit_FunctionDef(node)  # type: ignore
