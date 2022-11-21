import ast

from nb_autodoc.annotation import (
    Annotation,
    AnnotationTransformer,
    CallableType,
    GASubscript,
    Literal,
    Name,
    TypingName,
    UnionType,
    _annexpr,
    _get_typing_normalizer,
)
from nb_autodoc.manager import _AnnContext


def get_expr(s: str) -> ast.expr:
    return ast.parse(s, mode="eval").body


class TestAnnotationTransformer:
    def test_string_flatten(self):
        norm = lambda x: None

        def transform(expr: ast.expr) -> _annexpr:
            return AnnotationTransformer(norm).visit(expr)

        assert transform(get_expr("'AnyName.Name'")) == Name("AnyName.Name")
        assert transform(get_expr("Dict['Union[int, str]', 'None']")) == GASubscript(
            Name("Dict"), [GASubscript(Name("Union"), [Name("int"), Name("str")]), None]
        )

    def test_typing_common(self):
        anncontext = _AnnContext(
            ["t"],
            {
                "t_Union": "Union",
                "Union": "Union",
                "t_Literal": "Literal",
                "Tuple": "Tuple",
                "Callable": "Callable",
            },
        )

        def transform(expr: ast.expr) -> _annexpr:
            return AnnotationTransformer(_get_typing_normalizer(anncontext)).visit(expr)

        # Union test
        assert transform(
            get_expr("t.Union[t_Union[Union[int, str], A | B], A]")
        ) == UnionType([Name("int"), Name("str"), Name("A"), Name("B")])
        # Literal test
        assert transform(get_expr("t_Literal['^_^', True, enum.A]")) == Literal(
            ["^_^", True, Name("enum.A")]
        )
        # Tuple test
        assert transform(get_expr("Tuple[()]")) == GASubscript(
            TypingName("Tuple", "Tuple"), []
        )
        assert transform(get_expr("t.Tuple[int, str]")) == GASubscript(
            TypingName("t.Tuple", "Tuple"), [Name("int"), Name("str")]
        )
        assert transform(get_expr("Tuple[str, ...]")) == GASubscript(
            TypingName("Tuple", "Tuple"), [Name("str"), ...]
        )
        # Callable test
        assert transform(get_expr("Callable[[], t.Any]")) == CallableType(
            [], TypingName("t.Any", "Any")
        )
        assert transform(get_expr("Callable[..., A]")) == CallableType(..., Name("A"))
        assert transform(
            get_expr("Callable[t.Concatenate[int, ...], A]")
        ) == CallableType(
            GASubscript(TypingName("t.Concatenate", "Concatenate"), [Name("int"), ...]),
            Name("A"),
        )
