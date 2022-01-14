import ast
import inspect
from typing import Any, Callable, List, Dict, Union, Optional
from copy import deepcopy
from random import randint
from inspect import Parameter, Signature

from nb_autodoc.schema import OverloadFunctionDef
from nb_autodoc.pycode.unparser import unparse


class force_repr:
    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        self.value = value

    def __repr__(self) -> str:
        return self.value


def extract_all_overloads(
    source: str, *, globals: Optional[Dict[str, Any]] = None
) -> "OverloadPicker":
    """
    Args:
        globals: the context for executing object.
    """
    picker = OverloadPicker(globals or source)
    astmodule = ast.parse(source)
    picker.visit(astmodule)
    return picker


def signature_from_ast(node: ast.FunctionDef) -> Signature:
    args = node.args
    params: List[Parameter] = []
    defaults = args.defaults.copy()
    kwdefaults = args.kw_defaults
    non_default_count = len(args.args) - len(defaults)
    for arg in args.args[:non_default_count]:
        params.append(
            Parameter(
                arg.arg,
                kind=Parameter.POSITIONAL_OR_KEYWORD,
                annotation=(
                    force_repr(unparse(arg.annotation))
                    if arg.annotation
                    else Parameter.empty
                ),
            )
        )
    for i, arg in enumerate(args.args[non_default_count:]):
        params.append(
            Parameter(
                arg.arg,
                kind=Parameter.POSITIONAL_OR_KEYWORD,
                default=unparse(defaults[i]),
                annotation=(
                    force_repr(unparse(arg.annotation))
                    if arg.annotation
                    else Parameter.empty
                ),
            )
        )
    if args.vararg:
        params.append(
            Parameter(
                args.vararg.arg,
                kind=Parameter.VAR_POSITIONAL,
                annotation=(
                    force_repr(unparse(args.vararg.annotation))
                    if args.vararg.annotation
                    else Parameter.empty
                ),
            )
        )
    for i, arg in enumerate(args.kwonlyargs):
        default = kwdefaults[i]
        params.append(
            Parameter(
                arg.arg,
                kind=Parameter.KEYWORD_ONLY,
                default=(force_repr(unparse(default)) if default else Parameter.empty),
                annotation=(
                    force_repr(unparse(arg.annotation))
                    if arg.annotation
                    else Parameter.empty
                ),
            )
        )
    if args.kwarg:
        params.append(
            Parameter(
                args.kwarg.arg,
                kind=Parameter.VAR_KEYWORD,
                annotation=(
                    force_repr(unparse(args.kwarg.annotation))
                    if args.kwarg.annotation
                    else Parameter.empty
                ),
            )
        )
    return_anno = force_repr(unparse(node.returns)) if node.returns else Parameter.empty
    return Signature(params, return_annotation=return_anno)


class OverloadPicker(ast.NodeVisitor):
    """
    Python ast visitor to pick up overload function signature and docstring.
    """

    def __init__(
        self, source: Union[Dict[str, Any], str], encoding: str = "utf-8"
    ) -> None:
        self.encoding = encoding
        self.context: List[str] = []
        self.current_function: Optional[ast.FunctionDef] = None
        self.current_class: Optional[ast.ClassDef] = None
        self.overloads: Dict[str, List[OverloadFunctionDef]] = {}
        self.globals: Dict[str, Any] = {}
        self.typing: List[str] = []
        self.typing_overload: List[str] = []
        super().__init__()
        if isinstance(source, str):
            try:
                exec(source, self.globals)
            except Exception:
                pass
        elif isinstance(source, dict):
            self.globals = source.copy()

    def is_overload(self, node: ast.FunctionDef) -> bool:
        overload_ids = [f"{i}.overload" for i in self.typing] + self.typing_overload
        for decorator in node.decorator_list:
            if unparse(decorator) in overload_ids:
                return True
        return False

    def exec_safety(self, node: ast.FunctionDef) -> Callable:
        """Safely exec source code by giving a random fake name."""
        node = deepcopy(node)
        newname = self.get_safety_function_name()
        node.name = newname
        source = unparse(node)
        globals = self.globals.copy()
        exec(source, globals)
        return globals[newname]

    def get_safety_function_name(self, a: int = 0, b: int = 10000000) -> str:
        """Generate random function name, maybe unreliable."""
        s = f"nb1API{randint(a, b)}"
        while s in self.globals:
            s = f"nb1API{randint(a, b)}"
        return s

    def get_qualname_for(self, name: str) -> str:
        if self.current_class:
            return f"{self.current_class.name}.{name}"
        return name

    def get_signature(self, node: ast.FunctionDef) -> Signature:
        node = deepcopy(node)
        node.decorator_list.clear()
        unwrap_obj = self.exec_safety(node)
        if not callable(unwrap_obj):
            raise TypeError(f"Unknown type: {type(unwrap_obj)}")
        signature = inspect.signature(unwrap_obj)
        return signature

    def get_docstring(self, node: ast.FunctionDef) -> str:
        docstring = ""
        fst = node.body[0]
        if isinstance(fst, ast.Expr) and isinstance(fst.value, ast.Str):
            if isinstance(fst.value.s, str):
                docstring = fst.value.s
        return inspect.cleandoc(docstring)

    def visit_Import(self, node: ast.Import) -> None:
        for name in node.names:
            if name.name == "typing":
                self.typing.append(name.asname or name.name)
            elif name.name == "typing.overload":
                self.typing_overload.append(name.asname or name.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for name in node.names:
            if node.module == "typing" and name.name == "overload":
                self.typing_overload.append(name.asname or name.name)

    def visit_Try(self, node: ast.Try) -> None:
        # ignore try stmt special in module
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # ignore class inner class and avoid re-cover
        if self.current_class is None:
            self.current_class = node
            self.context.append(node.name)
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.visit(child)
            self.context.pop()
            self.current_class = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # ignore function inner function and avoid re-cover
        if self.current_function is None:
            qualname = self.get_qualname_for(node.name)
            self.current_function = node
            self.context.append(node.name)
            if self.is_overload(node):
                try:
                    signature = self.get_signature(node)
                except:
                    signature = signature_from_ast(node)
                docstring = self.get_docstring(node)
                overload = OverloadFunctionDef(
                    ast=node, signature=signature, docstring=docstring
                )
                self.overloads.setdefault(qualname, []).append(overload)
            self.context.pop()
            self.current_function = None

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)  # type: ignore
