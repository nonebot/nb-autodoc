import ast
import importlib
import itertools
import sys
import typing as t
from contextlib import contextmanager

from nb_autodoc.log import logger
from nb_autodoc.utils import resolve_name

T = t.TypeVar("T")


def ast_parse(source: str, filename: str = "<unknown>") -> ast.Module:
    """AST parse function with mode "exec" and type_comments feature.

    Argument filename is only used for logging.
    """
    try:
        return ast.parse(source, type_comments=True)
    except SyntaxError:
        logger.exception(f"unable to parse file {filename}")
        # Invalid type comment: https://github.com/sphinx-doc/sphinx/issues/8652
        return ast.parse(source)
    except TypeError:
        # Fallback
        return ast.parse(source)


@t.overload
def ast_unparse(node: ast.AST) -> str:
    ...


@t.overload
def ast_unparse(node: ast.AST, _default: str) -> str:
    ...


def ast_unparse(node: ast.AST, _default: t.Optional[str] = None) -> str:
    # TODO: implement ast.expr / ast.Expression unparser
    if sys.version_info >= (3, 8):
        # Or get_source_segment?
        return ast.unparse(node)
    if _default is None:
        raise
    return _default


# Although python compat node in previous version
# It's not good idea to fixup and return correct node
def is_constant_node(node: ast.expr) -> bool:
    if sys.version_info >= (3, 8):
        return isinstance(node, ast.Constant)
    return isinstance(
        node, (ast.Num, ast.Str, ast.Bytes, ast.NameConstant, ast.Ellipsis)
    )


def get_constant_value(node: ast.expr) -> t.Any:
    if sys.version_info < (3, 8) and isinstance(node, ast.Ellipsis):
        return ...
    return getattr(node, node._fields[0])  # generic


# Resolve complex assign like `a, b = c, d = 1, 2`
def get_assign_targets(node: t.Union[ast.Assign, ast.AnnAssign]) -> t.List[ast.expr]:
    if isinstance(node, ast.Assign):
        return node.targets
    else:
        return [node.target]


def get_target_names(node: ast.expr, self: str = "") -> t.List[str]:
    """Get `[a, b, c]` from a target `(a, (b, c))`."""
    if self:
        if isinstance(node, ast.Attribute):
            # Get `attr` from a target `self.attr`
            if isinstance(node.value, ast.Name) and node.value.id == self:
                return [node.attr]
        return []  # Error docstring in class.__init__
    if isinstance(node, ast.Name):
        return [node.id]
    elif isinstance(node, (ast.List, ast.Tuple)):
        return list(
            itertools.chain.from_iterable(get_target_names(elt) for elt in node.elts)
        )
    # Not new variable creation
    return []


class ImportFailed(t.NamedTuple):
    module: str
    name: str
    asname: t.Optional[str]  # useless as it always represents in key


def eval_import_stmts(
    stmts: t.List[ast.stmt], package: t.Optional[str] = None
) -> t.Tuple[t.Dict[str, t.Any], t.Dict[str, ImportFailed]]:
    """Evaluate `ast.Import` or `ast.ImportFrom` using importlib.

    Return is tuple of imported namespace and failed namespace.

    This function will catch all ImportError and pass, and return failed namespace
    specially for ImportFrom.
    """
    imported: t.Dict[str, t.Any] = {}
    failed_from_import: t.Dict[str, ImportFailed] = {}
    for stmt in stmts:
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                try:
                    imported[alias.asname or alias.name.split(".")[0]] = __import__(
                        alias.name
                    )
                except ImportError:
                    pass
        elif isinstance(stmt, ast.ImportFrom):
            for alias in stmt.names:
                if alias.name == "*":
                    break
                from_module_name = resolve_name(stmt, package)
                varname = alias.asname or alias.name
                try:
                    from_module = importlib.import_module(from_module_name)
                    if alias.name in from_module.__dict__:
                        imported[varname] = from_module.__dict__[alias.name]
                    else:
                        imported[varname] = importlib.import_module(
                            from_module_name + "." + alias.name
                        )
                except ImportError:
                    failed_from_import[varname] = ImportFailed(
                        from_module_name, alias.name, alias.asname
                    )
    return imported, failed_from_import


def interleave(
    inter: t.Callable[[], None], f: t.Callable[[T], None], seq: t.Iterable[T]
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


class Unparser(ast.NodeVisitor):
    """Utilities like `ast._Unparser` in py3.9+.

    Subclassing this class and implement the unparse method.
    """

    def __init__(self) -> None:
        self._source: t.List[str] = []

    def traverse(self, node: ast.AST) -> None:
        """Alternative call for `super().visit()` since `visit` is overridden.

        Unlike ast._Unparser.traverse, this do not accept list argument for concision.
        """
        super().visit(node)

    def visit(self, node: ast.AST) -> str:
        self._source = []
        self.traverse(node)
        return "".join(self._source)

    @t.final
    def write(self, s: str) -> None:
        self._source.append(s)

    @t.final
    @contextmanager
    def delimit(self, start: str, end: str) -> t.Generator[None, None, None]:
        self.write(start)
        yield
        self.write(end)
