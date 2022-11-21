import ast
import itertools
import sys
from collections import defaultdict
from dataclasses import dataclass, field, replace
from inspect import Signature
from typing import Dict, List, NamedTuple, Optional, Union, cast

from .utils import (
    get_assign_names,
    get_constant_value,
    get_docstring,
    is_constant_node,
    resolve_name,
    signature_from_ast,
    unparse_attribute_or_name,
)

_Member = Union["ImportFromData", "AssignData", "FunctionDefData", "ClassDefData"]


@dataclass
class ModuleData:
    scope: Dict[str, _Member] = field(default_factory=dict)
    type_checking_body: List[ast.stmt] = field(default_factory=list, compare=False)
    # type_checking_names: Dict[str, None] = field(default_factory=dict)
    # NOTE: typing import is only supported in Module frame
    typing_module: List[str] = field(default_factory=list)
    # names is Mapping of `varname: name`
    typing_names: Dict[str, str] = field(default_factory=dict)


@dataclass
class ImportFromData:
    order: int
    name: str  # varname
    module: str
    orig_name: str


@dataclass
class AssignData:
    # store both ast.Assign and ast.AnnAssign
    order: int
    name: str
    annotation: Optional[ast.expr] = field(default=None, compare=False)
    type_comment: Optional[str] = None
    docstring: Optional[str] = None
    # NOTE: field to specify whether a AnnAssign has value can be used to
    # check instance var, but we check its runtime existence.

    def merge(self, other: "AssignData") -> "AssignData":
        # used in merging `__init__` level AssignData into class-level AssignData
        new = replace(self)
        if not new.docstring and other.docstring:
            new.docstring = other.docstring
        if other.annotation:
            new.annotation = other.annotation
        if other.type_comment:
            new.type_comment = other.type_comment
        return new


class _overload(NamedTuple):
    signature: Signature
    docstring: Optional[str]


@dataclass
class FunctionDefData:
    order: int
    name: str
    # None if function has no impl
    signature: Optional[Signature] = field(default=None, compare=False)
    overloads: List[_overload] = field(default_factory=list)
    # don't pick docstring from ast because unreliable


@dataclass
class ClassDefData:
    order: int
    name: str
    scope: Dict[str, _Member] = field(default_factory=dict)
    # instance vars is only picked from `class.__init__`
    # class decl is stored in `class.__annotations__`
    instance_vars: Dict[str, AssignData] = field(default_factory=dict)
    methods: Dict[str, FunctionDefData] = field(default_factory=dict)
    type_checking_body: List[ast.stmt] = field(default_factory=list, compare=False)
    # type_checking_names: Dict[str, None] = field(default_factory=dict)


class DefinitionFinder:
    """Find all binding names, variable comments, type comments and annotations.

    The following patterns bind names:

    - class or function definition
    - assignment expression (:=)
    - targets that create new variable
    - import statement
    - compound statement body (if, while, for, try, with, match)
    - See: https://docs.python.org/3/reference/executionmodel.html#naming-and-binding

    We bind names on `from...import`, `new variable declaration`, `function or class`

    **Variable comment:**

    In pyright, variable comment is bound on its first definition (or decl).
    But we bind comment that first appears in multiple definitions.

    Just like:
    ```python
    a: int
    a = 1
    "a docstring is OK."
    a = 2
    "a docstring re-definition is ignored."
    ```

    Before nb_autodoc v0.2.0, `#:` special comment syntax is allowed.
    See: https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html
    Now it is deprecated for implicit meaning and irregular syntax.

    If assignment has multiple names like `a, b = 1, 2`, its docstring and type comment
    will be assigned to each name.
    """

    def __init__(self, *, package: Optional[str]) -> None:
        self.package = package  # maybe null
        """Package name. Resolve relative import."""
        self.next_stmt: Optional[ast.stmt] = None
        self.current_classes: List[ClassDefData] = []
        self.current_function: Optional[ast.FunctionDef] = None
        self.in_type_checking: bool = False
        self.counter = itertools.count()
        self.module = ModuleData()
        # conventional attr
        self.imp_typing = self.module.typing_module
        self.imp_typing_names = self.module.typing_names

    def get_current_frame(self) -> Union[ModuleData, ClassDefData]:
        if self.current_classes:
            return self.current_classes[-1]
        else:
            return self.module

    def get_self(self) -> Optional[str]:
        """Return the first argument name in a method if exists."""
        if self.current_classes and self.current_function:
            if sys.version_info >= (3, 8) and self.current_function.args.posonlyargs:
                return self.current_function.args.posonlyargs[0].arg
            if self.current_function.args.args:
                return self.current_function.args.args[0].arg
        return None

    def get_typing_ids(self, tp_id: str) -> List[str]:
        return [f"{i}.{tp_id}" for i in self.imp_typing] + [
            k for k, v in self.imp_typing_names.items() if v == tp_id
        ]

    def is_overload(self, node: ast.FunctionDef) -> bool:
        overload_ids = self.get_typing_ids("overload")
        for deco in node.decorator_list:
            deco_str = unparse_attribute_or_name(deco)
            if deco_str is not None:
                if deco_str in overload_ids:
                    return True
        return False

    def visit(self, node: ast.AST) -> None:
        """Visit a concrete node."""
        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, None)
        if visitor:  # disallow generic visit
            visitor(node)

    def visit_body(self, body: List[ast.stmt]) -> None:
        """Traversal visit node and record peek next node."""
        for index in range(len(body)):
            self.next_stmt = body[index + 1] if index + 1 < len(body) else None
            self.visit(body[index])

    def visit_Module(self, node: ast.Module) -> None:
        self.visit_body(node.body)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self.current_function:
            return
        scope = self.get_current_frame().scope
        function_data = scope.get(node.name)
        if not isinstance(function_data, FunctionDefData):
            function_data = FunctionDefData(next(self.counter), node.name)
        if self.is_overload(node):
            function_data.overloads.append(
                _overload(
                    signature_from_ast(node.args, node.returns), get_docstring(node)
                )
            )
        else:
            function_data.signature = signature_from_ast(node.args, node.returns)
        self.current_function = node
        if self.current_classes and node.name == "__init__":
            self.visit_body(node.body)
        self.current_function = None
        scope[node.name] = function_data

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return self.visit_FunctionDef(node)  # type: ignore

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self.current_function:
            return
        class_data = ClassDefData(next(self.counter), node.name)
        self.current_classes.append(class_data)
        self.visit_body(node.body)
        self.current_classes.pop()
        scope = self.get_current_frame().scope
        scope[node.name] = class_data

    def visit_Assign(self, node: ast.Assign) -> None:
        self_id = self.get_self()
        names = get_assign_names(node, self_id)
        if self_id:
            # __init__ definition needs a special scope
            scope = cast("dict[str, _Member]", self.current_classes[-1].instance_vars)
        else:
            scope = self.get_current_frame().scope
        type_comment = getattr(node, "type_comment", None)
        docstring = None
        next_stmt = self.next_stmt
        if isinstance(next_stmt, ast.Expr) and is_constant_node(next_stmt.value):
            docstring = get_constant_value(next_stmt.value)
            # if isinstance(docstring, bytes):
            #     docstring = docstring.decode()
            if not isinstance(docstring, str):
                docstring = None
        for name in names:
            assign_data = scope.get(name)
            # if exists overloads, then ignore, otherwise create and cover
            if isinstance(assign_data, FunctionDefData) and assign_data.overloads:
                continue
            elif not isinstance(assign_data, AssignData):
                assign_data = AssignData(next(self.counter), name)
                scope[name] = assign_data
            # bind annotation and type_comment to its last declaration
            if isinstance(node, ast.AnnAssign):
                assign_data.annotation = node.annotation
            if type_comment is not None:
                assign_data.type_comment = type_comment
            # bind docstring to its first declaration
            if docstring is not None and assign_data.docstring is None:
                assign_data.docstring = docstring

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        return self.visit_Assign(node)  # type: ignore

    def visit_If(self, node: ast.If) -> None:
        test = unparse_attribute_or_name(node.test)
        if test:
            type_checking_ids = self.get_typing_ids("TYPE_CHECKING")
            if test in type_checking_ids and not self.in_type_checking:
                # don't enter nested TYPE_CHECKING condition
                self.in_type_checking = True
                if self.current_classes:
                    type_checking_body = self.current_classes[-1].type_checking_body
                else:
                    type_checking_body = self.module.type_checking_body
                type_checking_body.extend(node.body)
        self.visit_body(node.body)
        self.in_type_checking = False

    def visit_Import(self, node: ast.Import) -> None:
        if self.current_function or self.current_classes:
            # only analyze module-level import
            return
        # do not add definition
        for alias in node.names:
            if alias.name in ("typing", "typing_extensions"):
                # just make symbol typing import
                self.imp_typing.append(alias.asname or alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self.current_function:
            return
        if not self.current_classes and node.module in ("typing", "typing_extensions"):
            # only analyze module-level importfrom
            for alias in node.names:
                self.imp_typing_names[alias.asname or alias.name] = alias.name
        absoluate_module = resolve_name(node, self.package)
        # add definition
        scope = self.get_current_frame().scope
        for alias in node.names:
            varname = alias.asname or alias.name
            scope[varname] = ImportFromData(
                next(self.counter), varname, absoluate_module, alias.name
            )

    # def visit_Expr(self, node: ast.Expr) -> None:
    #     # bound docstring on previous assign
    #     if previous and isinstance(previous, (ast.Assign, ast.AnnAssign)):
    #         names = get_assign_names(previous, self.get_self())
    #         scope = self.get_current_scope()
    #         assign_data: AssignData
    #         for assign_data in map(scope.__getitem__, names):
    #             if assign_data.docstring is None:
    #                 assign_data.docstring = docstring
