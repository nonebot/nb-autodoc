"""Analyze AST annotation without execution.

There are three parts of annotation analyzer:

1. build abstract annotation
2. evaluate name from t_globals and specify typealias
3. build doc repr without actually running evaluation

Note: static annotation analysis needs to build a big type system.
And function annotation depends on its definition (needs inferer).

"""
from __future__ import annotations

import ast
import typing as t
import typing_extensions as te

from nb_autodoc.analyzers.utils import (
    get_constant_value,
    get_subst_args,
    is_constant_node,
    unparse_attribute_or_name,
)

if t.TYPE_CHECKING:
    from nb_autodoc.manager import _AnnContext
    from nb_autodoc.typing import T_Annot, T_GenericAlias


t_all_definitions = {k: getattr(t, k) for k in t.__all__}
te_all_definitions = {k: getattr(te, k) for k in te.__all__}


def _evaluate(
    ann: T_Annot,
    globals: dict[str, t.Any] | None = None,
    locals: dict[str, t.Any] | None = None,
) -> T_GenericAlias | type | None:
    ...


# see: https://docs.python.org/3/library/stdtypes.html#standard-generic-classes
_py310_ga = {
    tuple: t.Tuple,
    list: t.List,
    dict: t.Dict,
    set: t.Set,
    frozenset: t.FrozenSet,
    type: t.Type,
}

_py310_ga_tpname = {"Tuple", "List", "Dict", "Set", "FrozenSet", "Type"}


class _annexpr:
    ...


class Name(_annexpr):
    def __init__(self, name: str) -> None:
        self.name = name

    # is TypeVar. just call __repr__
    # is normal class. repr class.__name__
    # is typealias. repr import name (not asname). solve reference on it
    # in typing.__dict__.values() is typing object

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Name):
            return False
        return self.name == other.name

    def __repr__(self) -> str:
        return self.name


class TypingName(_annexpr):
    def __init__(self, name: str, tp_name: str) -> None:
        self.name = name
        self.tp_name = tp_name

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TypingName):
            return False
        return self.name == other.name and self.tp_name == other.tp_name

    def __repr__(self) -> str:
        if self.tp_name in _py310_ga_tpname:
            return self.tp_name.lower()
        return self.tp_name


class UnionType(_annexpr):
    # typing.Union and py3.10 `X | Y`
    def __init__(self, args: list[_annexpr | None]) -> None:
        new_args = []
        for arg in args:
            if isinstance(arg, UnionType):
                new_args.extend(arg.args)
            elif arg not in new_args:
                # deduplicates
                new_args.append(arg)
        assert len(new_args) >= 2, "Union requires at least two types"
        self.args: list[_annexpr | None] = new_args

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UnionType):
            return False
        # order is respected
        return self.args == other.args

    def __repr__(self) -> str:
        return " | ".join(repr(arg) for arg in self.args)


# just typing for test
_literal_tp = t.Union[int, bool, str, bytes, None]


class Literal(_annexpr):
    def __init__(self, args: list[_literal_tp | Name]) -> None:
        # int, bool, str, bytes, None or enum
        # literal should not be dups and nested
        self.args = list(args)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Literal):
            return False
        return self.args == other.args

    def __repr__(self) -> str:
        return f"Literal[{', '.join(repr(arg) for arg in self.args)}]"


class Annotated(_annexpr):
    def __init__(self, origin: _annexpr) -> None:
        self.origin = origin

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Annotated):
            return False
        return self.origin == other.origin

    def __repr__(self) -> str:
        return repr(self.origin)


class GASubscript(_annexpr):
    # origin is class. repr class.__name__
    def __init__(
        self, origin: Name | TypingName, args: list[_annexpr | ellipsis | None]
    ) -> None:
        # origin is TypingName don't need evaluation
        self.origin = origin
        self.args = args

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GASubscript):
            return False
        return self.origin == other.origin and self.args == other.args

    def __repr__(self) -> str:
        return f"{self.origin!r}[{', '.join(repr(arg) for arg in self.args)}]"


class CallableType(_annexpr):
    def __init__(
        self, args: list[_annexpr] | ellipsis | GASubscript | Name, ret: _annexpr | None
    ) -> None:
        # Callable[[arg1, arg2], None]
        # Callable[..., Any]
        # Callable[Concatenate[P, int], None]
        # Callable[P, None]
        self.args = args
        self.ret = ret

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CallableType):
            return False
        return self.args == other.args and self.ret == other.ret

    def __repr__(self) -> str:
        if self.args is ...:  # mypy mistake ...
            params = "..."
        elif isinstance(self.args, (GASubscript, Name)):
            params = repr(self.args)
        else:
            params = ", ".join(repr(arg) for arg in self.args)  # type: ignore
        # make parents on union return because https://bugs.python.org/issue43609
        ret = f"({self.ret!r})" if isinstance(self.ret, UnionType) else repr(self.ret)
        return f"({params}) -> {ret}"


class AnnotationTransformer(ast.NodeVisitor):  # type hint
    def __init__(self, norm_typing_name: t.Callable[[str], str | None]) -> None:
        self.norm_typing_name = norm_typing_name

    def visit(self, node: ast.expr) -> t.Any:  # type: ignore[override]
        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, None)
        if visitor:  # disallow generic visit
            return visitor(node)
        raise TypeError(f"try to visit invalid annotation node {method}")

    def visit_BinOp(self, node: ast.BinOp) -> UnionType:
        if not isinstance(node.op, ast.BitOr):
            raise TypeError("only support 'X | Y' BinOp")
        left = self.visit(node.left)
        right = self.visit(node.right)
        return UnionType([left, right])

    def visit_Constant(self, node: ast.Constant) -> _annexpr | ellipsis | None:
        """Parse and dispatch string annotation."""
        if is_constant_node(node):
            value = get_constant_value(node)
            if isinstance(value, str):
                # Literal or Annotated may contains quotes
                # so we can't replace quotes to parse ForwardRef
                return self.visit(ast.parse(value, mode="eval").body)
            elif value in (None, ...):
                return value
            raise TypeError(f"unsupported Constant node type {type(value)}")
        raise RuntimeError

    def visit_Attribute(self, node: ast.Attribute | ast.Name) -> Name | TypingName:
        name = unparse_attribute_or_name(node)
        if not name:
            raise TypeError("Attribute is not dotted name")
        typing_name = self.norm_typing_name(name)
        if typing_name:
            return TypingName(name, typing_name)
        return Name(name)

    def visit_Name(self, node: ast.Name) -> Name:
        return self.visit_Attribute(node)  # type: ignore

    def visit_Subscript(self, node: ast.Subscript) -> _annexpr:
        # Subscript is not generic subscript if it is typing indicator
        origin = self.visit(node.value)
        if not isinstance(origin, (Name, TypingName)):
            # maybe add some AST info
            msg = "Subscript value is not a dotted name"
            raise TypeError(msg)
        args = get_subst_args(node)
        if isinstance(origin, TypingName):
            return self.dispatch_typing_subst(origin, args)
        return GASubscript(origin, [self.visit(i) for i in args])

    visit_Str = visit_Constant
    visit_Ellipsis = visit_Constant  # maybe string so generic visit
    visit_NameConstant = visit_Constant

    def dispatch_typing_subst(self, name: TypingName, args: list[ast.expr]) -> _annexpr:
        method = getattr(self, f"typing_{name.tp_name}", None)
        if method:
            return method(args)
        return GASubscript(name, [self.visit(i) for i in args])

    def typing_Union(self, args: list[ast.expr]) -> UnionType:
        return UnionType([self.visit(i) for i in args])

    def typing_Optional(self, args: list[ast.expr]) -> UnionType:
        assert len(args) == 1, "Optional requires single parameter"
        return UnionType([self.visit(args[0]), None])

    # the typing indicators that require special treatment
    def typing_Literal(self, args: list[ast.expr]) -> Literal:
        new_args = []
        for expr in args:
            if is_constant_node(expr):
                new_args.append(get_constant_value(expr))
            else:
                annexpr = self.visit(expr)
                if not isinstance(annexpr, Name):
                    raise TypeError("Literal requires Constant or enum")
                new_args.append(annexpr)
        return Literal(new_args)

    def typing_Annotated(self, args: list[ast.expr]) -> Annotated:
        return Annotated(self.visit(args[0]))

    def typing_Callable(self, args: list[ast.expr]) -> CallableType:
        assert len(args) == 2, "Callable must be Callable[[arg, ...], ret]"
        ret = self.visit(args[1])
        call_args: ellipsis | list[_annexpr] | GASubscript
        if isinstance(args[0], ast.List):
            call_args = [self.visit(i) for i in args[0].elts]
        else:
            call_args = self.visit(args[0])
            if (
                call_args is ...
                or isinstance(call_args, Name)
                or (
                    isinstance(call_args, GASubscript)
                    and isinstance(call_args.origin, TypingName)
                    and call_args.origin.tp_name == "Concatenate"
                )
            ):
                pass
            else:
                raise TypeError(
                    "Callable[arg, ret] arg requires ellipsis, List, ParamSpec or Concatenate"
                )
        return CallableType(call_args, ret)


def _get_typing_normalizer(context: _AnnContext) -> t.Callable[[str], str | None]:
    def _norm_typing_name(name: str) -> str | None:
        if name in context.typing_names:
            return context.typing_names[name]
        module, dot, attr = name.partition(".")
        if dot and module in context.typing_module:
            return attr

    return _norm_typing_name


def _ga_subst_outer_check(ann: _annexpr, tp_name: str) -> bool:
    if isinstance(ann, GASubscript) and isinstance(ann.origin, TypingName):
        return ann.origin.tp_name == tp_name
    return False


class Annotation:
    def __init__(self, ast_expr: ast.expr, context: _AnnContext) -> None:
        norm = _get_typing_normalizer(context)
        self.ann: _annexpr = AnnotationTransformer(norm).visit(ast_expr)

    @property
    def is_typealias(self) -> bool:
        if not isinstance(self.ann, TypingName):
            return False
        return self.ann.tp_name == "TypeAlias"

    @property
    def is_classvar(self) -> bool:
        return _ga_subst_outer_check(self.ann, "ClassVar")

    # @property
    # def is_callable(self) -> bool:
    #     # check if assign target is user function?
    #     return _ga_subst_outer_check(self.ann, "Callable")

    def type_link(self, ontype: t.Callable[[type], str]) -> str:
        ...

    def docuify(self, typealias: t.Dict[str, t.Tuple[str, str]]) -> str:
        ...
