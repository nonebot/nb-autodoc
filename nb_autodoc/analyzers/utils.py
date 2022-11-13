import ast
import importlib
import itertools
import sys
import typing as t
from contextlib import contextmanager
from importlib.util import resolve_name as imp_resolve_name
from inspect import Parameter, Signature

from nb_autodoc.log import logger

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


### For analyzers

# Although python compat node in previous version
# It's not good idea to fixup and return correct node
def is_constant_node(node: ast.expr) -> bool:
    if sys.version_info >= (3, 8):
        # some duck check
        return node.__class__.__name__ == "Constant"
    return node.__class__.__name__ in (
        "Num",
        "Str",
        "Bytes",
        "NameConstant",
        "Ellipsis",
    )


def get_constant_value(node: ast.expr) -> t.Any:
    if node.__class__.__name__ == "Ellipsis":
        return ...
    return getattr(node, node._fields[0])  # generic


# Resolve complex assign like `a, b = c, d = 1, 2`
def get_assign_targets(node: t.Union[ast.Assign, ast.AnnAssign]) -> t.List[ast.expr]:
    if isinstance(node, ast.Assign):
        return node.targets
    else:
        return [node.target]


def get_target_names(
    node: ast.expr, self_id: t.Optional[str] = None
) -> t.Tuple[str, ...]:
    """Get `(a, b, c)` from a target `(a, (b, c))`."""
    if self_id:
        if isinstance(node, ast.Attribute):
            # Get `attr` from a target `self.attr`
            if isinstance(node.value, ast.Name) and node.value.id == self_id:
                return (node.attr,)
        return ()
    elif isinstance(node, ast.Name):
        return (node.id,)
    elif isinstance(node, (ast.List, ast.Tuple)):
        return tuple(
            itertools.chain.from_iterable(
                get_target_names(elt, self_id) for elt in node.elts
            )
        )
    # Not new variable creation
    return ()


# @typed_lru_cache(1)
def get_assign_names(
    node: t.Union[ast.Assign, ast.AnnAssign], self_id: t.Optional[str] = None
) -> t.Tuple[str, ...]:
    """Get names `(a, b, c, d)` from complex assignment `a, b = c, d = 1, 2`.

    This function is `cache_size=1`.
    """
    return tuple(
        itertools.chain.from_iterable(
            get_target_names(i, self_id) for i in get_assign_targets(node)
        )
    )


### For components


def resolve_name(
    name_or_import: t.Union[ast.ImportFrom, str], package: t.Optional[str] = None
) -> str:
    """Resolve a relative module name to an absolute one."""
    if isinstance(name_or_import, ast.ImportFrom):
        name_or_import = "." * name_or_import.level + (name_or_import.module or "")
    return imp_resolve_name(name_or_import, package)


class ImportFromFailed(t.NamedTuple):
    module: str
    name: str
    asname: t.Optional[str]  # useless as it always represents in key


def eval_import_stmt(
    stmt: t.Union[ast.Import, ast.ImportFrom], package: t.Optional[str] = None
) -> t.Dict[str, t.Union[t.Any, ImportFromFailed]]:
    """Evaluate `ast.Import` or `ast.ImportFrom` using importlib.

    This function will catch `from...import` ImportError and create
    `ImportFromFailed` instance. Pass `import` ImportError.
    """
    imports: t.Dict[str, t.Union[t.Any, ImportFromFailed]] = {}
    if isinstance(stmt, ast.Import):
        for alias in stmt.names:
            try:
                imports[alias.asname or alias.name.split(".")[0]] = __import__(
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
                    imports[varname] = from_module.__dict__[alias.name]
                else:
                    imports[varname] = importlib.import_module(
                        from_module_name + "." + alias.name
                    )
            except ImportError:
                imports[varname] = ImportFromFailed(
                    from_module_name, alias.name, alias.asname
                )
    return imports


def get_docstring(
    node: t.Union[ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef]
) -> t.Optional[str]:
    """Return node raw docstring."""
    stmt = node.body[0]
    if isinstance(stmt, ast.Expr) and is_constant_node(stmt.value):
        docstring = get_constant_value(stmt.value)
        if isinstance(docstring, str):
            return docstring
        # elif isinstance(docstring, bytes):
        #     return docstring.decode()
    return None


def signature_from_ast(
    args: ast.arguments, returns: t.Optional[ast.expr] = None
) -> Signature:
    """Signature from ast. Stores original annotation expr in `Parameter.annotation`."""
    params = []
    defaults = args.defaults
    kwdefaults = args.kw_defaults
    non_default_count = len(args.args) - len(defaults)
    _empty = Parameter.empty
    if sys.version_info >= (3, 8):
        for arg in args.posonlyargs:
            params.append(
                Parameter(
                    arg.arg,
                    Parameter.POSITIONAL_ONLY,
                    annotation=arg.annotation or _empty,
                )
            )
    for index, arg in enumerate(args.args):
        params.append(
            Parameter(
                arg.arg,
                Parameter.POSITIONAL_OR_KEYWORD,
                default=(
                    _empty
                    if index < non_default_count
                    else defaults[index - non_default_count]
                ),
                annotation=arg.annotation or _empty,
            )
        )
    if args.vararg:
        arg = args.vararg
        params.append(
            Parameter(
                arg.arg,
                Parameter.VAR_POSITIONAL,
                annotation=arg.annotation or _empty,
            )
        )
    for i, arg in enumerate(args.kwonlyargs):
        params.append(
            Parameter(
                arg.arg,
                kind=Parameter.KEYWORD_ONLY,
                default=kwdefaults[i] or _empty,
                annotation=arg.annotation or _empty,
            )
        )
    if args.kwarg:
        arg = args.kwarg
        params.append(
            Parameter(
                arg.arg,
                kind=Parameter.VAR_KEYWORD,
                annotation=arg.annotation or _empty,
            )
        )
    # TODO: add type comment feature
    # in pyright, annotation has higher priority that type comment
    # https://peps.python.org/pep-0484/#suggested-syntax-for-python-2-7-and-straddling-code
    return Signature(params, return_annotation=returns or _empty)


def unparse_attribute_or_name(node: ast.expr) -> t.Optional[str]:
    """Unparse `name.attr` or `name`."""
    if isinstance(node, ast.Attribute):
        return f"{unparse_attribute_or_name(node.value)}.{node.attr}"
    elif isinstance(node, ast.Name):
        return node.id
    else:
        return None


class Unparser(ast.NodeVisitor):
    """Utilities like `ast._Unparser` in py3.9+.

    Subclassing this class and implement the unparse method.
    """

    _source: t.List[str]

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
    @staticmethod
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

    @t.final
    def write(self, s: str) -> None:
        self._source.append(s)

    @t.final
    @contextmanager
    def delimit(self, start: str, end: str) -> t.Generator[None, None, None]:
        self.write(start)
        yield
        self.write(end)
