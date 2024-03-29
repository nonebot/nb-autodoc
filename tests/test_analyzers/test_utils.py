import ast
import sys
from inspect import Parameter

from nb_autodoc.analyzers.utils import signature_from_ast


def test_signature_from_ast():
    def get_node(s: str) -> ast.FunctionDef:
        return ast.parse(f"def _{s}: ...").body[0]  # type: ignore

    def filter_non_empty(lst):
        return [i for i in lst if i is not Parameter.empty]

    _empty = Parameter.empty
    # POSITIONAL_ONLY appears in py3.3-, but ast supports it in py3.8+
    _posonly = Parameter.POSITIONAL_ONLY
    _arg = Parameter.POSITIONAL_OR_KEYWORD
    _vararg = Parameter.VAR_POSITIONAL
    _kwonly = Parameter.KEYWORD_ONLY
    _varkw = Parameter.VAR_KEYWORD

    node = get_node(
        "(a: www, b: _^w^_ = '<test>', *c: QAQ, d: QuQ, e: dict = {}, f: O.o, **g:-D) -> None"
    )
    signature = signature_from_ast(node.args, node.returns)
    params = dict(signature.parameters)
    kinds = [p.kind for p in params.values()]
    annotations = [p.annotation for p in params.values()]
    defaults = [p.default for p in params.values()]
    # do some ambitious check...because ast.AST has no `__eq__` implement
    assert type(signature.return_annotation) is ast.Constant
    assert list(params.keys()) == list("abcdefg")
    assert kinds == [_arg, _arg, _vararg, _kwonly, _kwonly, _kwonly, _varkw]
    assert [i.__class__ for i in annotations] == [
        ast.Name,
        ast.BinOp,
        ast.Name,
        ast.Name,
        ast.Name,
        ast.Attribute,
        ast.UnaryOp,
    ]
    assert [i.__class__ for i in filter_non_empty(defaults)] == [ast.Constant, ast.Dict]
    node = get_node("()")
    signature = signature_from_ast(node.args, node.returns)
    assert signature.return_annotation == _empty

    # posonly test for py3.8+
    if sys.version_info >= (3, 8):
        node = get_node("(a, /, b, c=1)")
        signature = signature_from_ast(node.args, node.returns)
        params = dict(signature.parameters)
        kinds = [p.kind for p in params.values()]
        assert list(params.keys()) == list("abc")
        assert kinds.count(_posonly) == 1
        assert kinds.count(_arg) == 2
        assert params["a"].default is Parameter.empty
        assert params["b"].default is Parameter.empty
        assert params["c"].default.__class__ is ast.Constant
