"""Python Code Analyzer by parsing and analyzing AST.

Stub file:

    Stub files are written in normal Python 3 syntax, but generally leaving out
    runtime logic like variable initializers, function bodies, and default arguments.

    So expected stub files are safe and executable. In the code analysis procedure,
    stub file do the same stuff as source file.

"""
import ast
import itertools
import linecache
import sys
from contextlib import contextmanager
from importlib import import_module
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from types import ModuleType
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    Iterable,
    List,
    Optional,
    Tuple,
    TypeVar,
    Union,
    overload,
)

from nb_autodoc.log import logger
from nb_autodoc.utils import resolve_name

T = TypeVar("T")


def ast_parse(source: str, filename: str = "<unknown>") -> ast.Module:
    """AST parse function with mode "exec".

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


@overload
def ast_unparse(node: ast.AST) -> str:
    ...


@overload
def ast_unparse(node: ast.AST, _default: str) -> str:
    ...


def ast_unparse(node: ast.AST, _default: Optional[str] = None) -> str:
    # TODO: implement ast.expr / ast.Expression unparser
    if sys.version_info >= (3, 8):
        # Or get_source_segment?
        return ast.unparse(node)
    if _default is None:
        raise
    return _default


class Analyzer:
    """Wrapper of variable comment picker and overload picker.

    Args:
        name: module name
        package: package name, useful in analyzing or performing import
        path: file path to analyze
        globalns: module's dictionary, evaluate from file if None
    """

    def __init__(
        self,
        name: str,
        package: Optional[str],
        path: Union[Path, str],
        *,
        globalns: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.name = name
        self.package = package
        self.path = str(path)
        if globalns is None:
            try:
                globalns = create_module_from_sourcefile(name, self.path).__dict__
            except Exception as e:
                raise ImportError(f"error raises executing {self.path}") from e
        self.globalns = globalns
        """Python code global namespace."""
        self.ann_ns = globalns.copy()
        """Namespace for annotation evaluation."""

        code = open(self.path, "r").read()
        self.tree = ast_parse(code, self.path)
        self.first_traverse_module()

    @property
    def filename(self) -> str:
        return Path(self.path).name

    @property
    def lines(self) -> List[str]:
        lines = linecache.getlines(self.path)
        if not lines:
            return linecache.updatecache(self.path, self.globalns)
        return lines

    def analyze(self) -> None:
        visitor = DefinitionFinder(self.name, self.package)
        visitor.visit(self.tree)
        self.definitions = visitor.definitions
        self.externals = visitor.externals
        self.comments = visitor.comments
        self.type_comments = visitor.type_comments
        self.annotations = visitor.annotations

    def first_traverse_module(self) -> None:
        """Find TYPE_CHECKING and evaluate it."""
        for stmt in self.tree.body:
            if isinstance(stmt, ast.If):
                if (
                    isinstance(stmt.test, ast.Name) and stmt.test.id == "TYPE_CHECKING"
                ) or (
                    is_constant_node(stmt.test)
                    and get_constant_value(stmt.test) == False
                ):
                    # Name is not resolved, only literal check
                    if is_constant_node(stmt.test):
                        logger.warning(
                            f"use TYPE_CHECKING instead of False",
                            (self.filename, stmt.lineno),
                        )
                    for st in filter(
                        lambda x: isinstance(x, (ast.Import, ast.ImportFrom)), stmt.body
                    ):
                        try:
                            self.ann_ns.__setitem__(*eval_import_stmt(st))
                        except ImportError:
                            logger.exception(
                                f"evaluate {st.__class__.__name__} failed",
                                (self.filename, st.lineno),
                            )

    def get_autodoc_literal(self) -> Dict[str, str]:
        """Get `__autodoc__` using `ast.literal_eval`."""
        logger.debug("searching __autodoc__...")
        for stmt in self.tree.body:
            if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                targets = get_assign_targets(stmt)
                if (
                    len(targets) == 1
                    and isinstance(targets[0], ast.Name)
                    and targets[0].id == "__autodoc__"
                ):
                    logger.debug("found __autodoc__ and evaluate")
                    if stmt.value is None:
                        raise ValueError("autodoc requires value")
                    return ast.literal_eval(stmt.value)
        logger.debug("no found __autodoc__")
        return {}


def eval_import_stmt(
    stmt: ast.stmt, package: Optional[str] = None
) -> Tuple[str, Union[ModuleType, Any]]:
    """Evaluate `ast.Import` or `ast.ImportFrom` using importlib."""
    if isinstance(stmt, ast.Import):
        for alias in stmt.names:
            return (alias.asname or alias.name.split(".")[0], __import__(alias.name))
    elif isinstance(stmt, ast.ImportFrom):
        for alias in stmt.names:
            if alias.name == "*":
                break
            varname = alias.asname or alias.name
            from_module_name = resolve_name(stmt, package)
            from_module = import_module(from_module_name)
            if alias.name in from_module.__dict__:
                return varname, from_module.__dict__[alias.name]
            else:
                return varname, import_module(from_module_name + "." + alias.name)
    raise ValueError(f"expect import node, got {type(stmt)}")


def create_module_from_sourcefile(modulename: str, path: str) -> ModuleType:
    """Create module from source file, this is useful for executing ".pyi" file.

    `importlib` supports suffixes like ".so" (extension_suffixes),
    ".py" (source_suffixes), ".pyc" (bytecode_suffixes).
    These extensions are recorded in `importlib._bootstrap_external`.
    """
    loader = SourceFileLoader(modulename, path)
    # spec_from_file_location without loader argument will skip invalid file extension
    spec = spec_from_loader(modulename, loader)
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


def get_target_names(node: ast.expr, self: str = "") -> List[str]:
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


_DEF_VISIT = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.ImportFrom)


class DefinitionFinder:
    """Pick variable comment, type comment and annotations.

    Before nb_autodoc v0.2.0, `#:` special comment syntax is allowed.
    See: https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html
    Now it is deprecated for implicit meaning and irregular syntax.

    If assign has multiple target like `a, b = 1, 2`, its docstring and type comment
    will be assigned to each name.

    Instance var in `A.__init__` saves in `A.__init__.a` format.
    """

    def __init__(self, name: str, package: Optional[str]) -> None:
        self.name = name
        """Relatively top-module name."""
        self.package = package
        """Package name."""
        self.ctx: List[str] = []
        self.previous: Optional[ast.AST] = None
        self.current_class: List[str] = []
        self.current_function: Optional[ast.FunctionDef] = None
        self.counter = itertools.count()
        self.definitions: Dict[str, int] = {}
        """Definition entry."""
        self.externals: Dict[str, str] = {}
        """External reference."""
        self.comments: Dict[str, str] = {}
        """Variable comment."""
        self.annotations: Dict[str, ast.Expression] = {}
        self.type_comments: Dict[str, ast.Expression] = {}

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
        self.comments[qualname] = comment

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
