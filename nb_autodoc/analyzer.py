"""Python Code Analyzer by parsing and analyzing AST.

Stub file:

    Stub files are written in normal Python 3 syntax, but generally leaving out
    runtime logic like variable initializers, function bodies, and default arguments.

    So expected stub files are safe and executable. In the code analysis procedure,
    stub file do the same stuff as source file.

"""
import ast
import itertools
import sys
from contextlib import contextmanager
from importlib import import_module
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, resolve_name, spec_from_loader
from pathlib import Path
from types import ModuleType
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    Iterable,
    List,
    NamedTuple,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

from nb_autodoc.utils import logger

T = TypeVar("T")


def ast_parse(source: str) -> ast.Module:
    """AST parse function, mode must be "exec" to avoid duplicated typing."""
    try:
        return ast.parse(source, type_comments=True)
    except SyntaxError:
        # Invalid type comment: https://github.com/sphinx-doc/sphinx/issues/8652
        return ast.parse(source)


class Analyzer:
    """Combination of definition finder, variable comment picker and overload picker.

    Args:
        fullname: module name
        package: package name, like fullname, useful when analyzing or performing import
        path: file path to analyze
        globalns: module's dictionary, evaluate from file if None
    """

    def __init__(
        self,
        fullname: str,
        package: Optional[str],
        path: Union[Path, str],
        *,
        globalns: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.code = open(path, "r").read()
        self.package = package
        self.module = ast_parse(self.code)
        self.type_refs: Dict[str, str] = {}
        """Store import and ClassDef refname for annotation analysis."""

        if globalns is None:
            try:
                globalns = create_module_from_sourcefile(fullname, str(path)).__dict__
            except Exception as e:
                raise ImportError(f"error raises evaluating {path}") from e
        self.globalns = globalns

        self.analyze()

    def analyze(self) -> None:
        for stmt in self.module.body:
            if (
                isinstance(stmt, ast.If)
                and isinstance(stmt.test, ast.Name)
                and stmt.test.id == "TYPE_CHECKING"
            ):
                # Name is not resolved, only literal check
                self.globalns.update(eval_import_stmts(stmt.body, self.package))
            # Clean function body for performance
            # NOTE: __init__ body cleaned
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                stmt.body[1:] = []


def eval_import_stmts(
    stmts: List[ast.stmt], package: Optional[str] = None
) -> Dict[str, Any]:
    """Evaluate `ast.Import` and `ast.ImportFrom` using importlib."""
    imported = {}
    for node in stmts:
        # Avoid exec and use import_module
        if isinstance(node, ast.Import):
            for alias in node.names:
                setname = alias.asname or alias.name
                imported[setname] = import_module(alias.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    break
                setname = alias.asname or alias.name
                from_module_name = resolve_name(
                    "." * node.level + (node.module or ""), package
                )
                module = import_module(from_module_name)
                if alias.name in module.__dict__:
                    imported[setname] = module.__dict__[alias.name]
                else:
                    imported[setname] = import_module(
                        "." + alias.name, from_module_name
                    )
    return imported


def create_module_from_sourcefile(fullname: str, path: str) -> ModuleType:
    """Create module from source file, this is useful for executing ".pyi" file.

    `importlib` supports suffixes like ".so" (extension_suffixes),
    ".py" (source_suffixes), ".pyc" (bytecode_suffixes).
    These extensions are recorded in `importlib._bootstrap_external`.
    """
    loader = SourceFileLoader(fullname, path)
    # spec_from_file_location without loader argument will skip invalid file extension
    spec = spec_from_loader(fullname, loader)
    if spec is None:  # only for type hints
        raise ImportError("no spec found")
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


# Although python compat node in previous version
# It's not good idea to fixup and return correct node
def is_constant_node(node: ast.expr) -> bool:
    if sys.version_info >= (3, 8):
        return isinstance(node, ast.Constant)
    return isinstance(
        node, (ast.Num, ast.Str, ast.Bytes, ast.NameConstant, ast.Ellipsis)
    )


def get_constant_value(node: ast.expr) -> Any:
    if sys.version_info < (3, 8) and isinstance(node, ast.Ellipsis):
        return ...
    return getattr(node, node._fields[0])  # generic


# Resolve complex assign like `a, b = c, d = 1, 2`
def get_assign_targets(node: Union[ast.Assign, ast.AnnAssign]) -> List[ast.expr]:
    if isinstance(node, ast.Assign):
        return node.targets
    else:
        return [node.target]


def get_target_names(node: ast.expr) -> List[str]:
    """Get `[a, b, c]` from a target `(a, (b, c))`."""
    if isinstance(node, ast.Name):
        return [node.id]
    elif isinstance(node, (ast.List, ast.Tuple)):
        return list(
            itertools.chain.from_iterable(get_target_names(elt) for elt in node.elts)
        )
    else:
        # Not new variable creation
        return []


def get_target_attr_from(node: ast.expr, name: str) -> Optional[str]:
    """Get `attr` from a target `self.attr`."""
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id == name:
            return node.attr
    return None


class AssignData(NamedTuple):
    comment: str
    type_comment: Optional[str]


def traverse_assign(
    node: Union[ast.Module, ast.ClassDef]
) -> Dict[Tuple[str, ...], AssignData]:
    """Traverse body and retrieve variable docstring and type_comment (if exists).

    Before nb_autodoc v0.2.0, `#:` special comment syntax is allowed.
    See: https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html
    Now it is deprecated for implicit meaning and irregular syntax.

    Returns:
        dict key is tuple of variable names, value is data tuple
    """
    res: Dict[Tuple[str, ...], AssignData] = {}
    for i, stmt in enumerate(node.body):
        if not isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            continue
        if i + 1 == len(node.body):
            continue
        next_stmt = node.body[i + 1]
        if isinstance(next_stmt, ast.Expr) and is_constant_node(next_stmt.value):
            docstring = get_constant_value(next_stmt.value)
            if isinstance(docstring, str):
                targets = get_assign_targets(stmt)
                names = tuple(
                    itertools.chain.from_iterable(get_target_names(i) for i in targets)
                )
                # invalid docstring if names empty...
                res[names] = AssignData(docstring, getattr(stmt, "type_comment", None))
    return res


def _traverse_docstring(node: Union[ast.Module, ast.ClassDef]) -> List[str]:
    # TODO: extract type comment only from `a = 1  # type: int`, attr or tuple assign not support
    docstrings: List[str] = []

    stmt = node.body[0]
    if is_constant_node(stmt):
        docstrings.append(_compat_get_text(stmt))

    for i, stmt in enumerate(node.body):
        if (
            isinstance(stmt, (ast.Assign, ast.AnnAssign))
            and (not i == len(node.body))
            and isinstance(node.body[i + 1], ast.Expr)
        ):
            expr = cast("ast.Expr", node.body[i + 1])
            if not _is_str_node(expr):
                continue
            docstrings.append(_compat_get_text(expr))
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and isinstance(
            stmt.body[0], ast.Expr
        ):
            expr = stmt.body[0]
            if not _is_str_node(expr):
                continue
            docstrings.append(_compat_get_text(expr))
        elif isinstance(stmt, ast.ClassDef):
            docstrings.extend(_traverse_docstring(stmt))

    return docstrings


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
    """Utilities like `ast._Unparser` in py3.9+.

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
    """Convert type annotation to new style."""
    try:
        node = ast.parse(s, mode="eval").body
    except SyntaxError:  # probably already new style
        return s
    return AnnotUnparser().visit(node)


class AnnotUnparser(_Unparser):
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
                self.write("...")
            elif isinstance(value, str):
                self.write(repr(str))
            elif value is None:
                self.write("None")
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
