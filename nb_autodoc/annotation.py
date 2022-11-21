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


class TypingName(_annexpr):
    def __init__(self, name: str, tp_name: str) -> None:
        self.name = name
        self.tp_name = tp_name

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TypingName):
            return False
        return self.name == other.name and self.tp_name == other.tp_name


class UnionType(_annexpr):
    # typing.Union and py3.10 `X | Y`
    def __init__(self, args: list[_annexpr | None]) -> None:
        new_args = []
        for arg in args:
            if isinstance(arg, UnionType):
                new_args.extend(arg.args)
            else:
                if arg not in new_args:
                    # deduplicates
                    new_args.append(arg)
        assert len(new_args) >= 2, "Union requires at least two types"
        self.args: list[_annexpr | None] = new_args

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UnionType):
            return False
        # order is respected
        return self.args == other.args


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


class CallableType(_annexpr):
    def __init__(
        self, args: list[_annexpr] | ellipsis | GASubscript, ret: _annexpr
    ) -> None:
        self.args = args
        self.ret = ret

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CallableType):
            return False
        return self.args == other.args and self.ret == other.ret


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

    def typing_Callable(self, args: list[ast.expr]) -> CallableType:
        assert len(args) == 2, "Callable must be Callable[[arg, ...], ret]"
        ret = self.visit(args[1])
        call_args: ellipsis | list[_annexpr] | GASubscript
        if isinstance(args[0], ast.List):
            call_args = [self.visit(i) for i in args[0].elts]
        else:
            concat = self.visit(args[0])
            if concat is ...:
                call_args = ...
            else:
                if (
                    not isinstance(concat, GASubscript)
                    or not isinstance(concat.origin, TypingName)
                    or concat.origin.tp_name != "Concatenate"
                ):
                    raise TypeError(
                        "Callable[arg, ret] arg requires ellipsis, List or Concatenate"
                    )
                call_args = concat
        return CallableType(call_args, ret)


def _get_typing_normalizer(context: _AnnContext) -> t.Callable[[str], str | None]:
    def _norm_typing_name(name: str) -> str | None:
        if name in context.typing_names:
            return context.typing_names[name]
        module, dot, attr = name.partition(".")
        if dot and module in context.typing_module:
            return attr

    return _norm_typing_name


class Annotation:
    def __init__(self, ast_expr: ast.expr, context: _AnnContext) -> None:
        self.ast_expr = ast_expr
        norm = _get_typing_normalizer(context)
        self.ann = AnnotationTransformer(norm).visit(ast_expr)
        self.norm_typing_name = norm

    @property
    def is_typealias(self) -> bool:
        if not isinstance(self.ann, TypingName):
            return False
        return self.ann.tp_name == "TypeAlias"

    def type_link(self, ontype: t.Callable[[type], str]) -> str:
        ...

    def stringify(self, typealias: t.Dict[str, t.Tuple[str, str]]) -> str:
        ...

    def __repr__(self) -> str:
        ...
