import ast

from nb_autodoc.annotation import (
    Annotated,
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
        assert transform(
            get_expr("Dict['Union[int, str]', 'None', Literal['int']]")
        ) == GASubscript(
            Name("Dict"),
            [
                GASubscript(Name("Union"), [Name("int"), Name("str")]),
                None,
                GASubscript(Name("Literal"), [Name("int")]),
            ],
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
        # Annotated test
        assert transform(
            get_expr("t.Annotated[A, (1, 2), ctypes('char')]")
        ) == Annotated(Name("A"))
        # Tuple test
        assert transform(get_expr("Tuple[()]")) == GASubscript(
            TypingName("Tuple", "Tuple"), []
        )
        assert transform(get_expr("t.Tuple[int, str]")) == GASubscript(
            TypingName("t.Tuple", "Tuple"), [Name("int"), Name("str")]
        )
        assert transform(get_expr("Tuple[str, '...']")) == GASubscript(
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

    def test_repr(self):
        assert (
            repr(
                GASubscript(
                    Name("Dict"),
                    [
                        GASubscript(Name("Union"), [Name("int"), Name("str")]),
                        None,
                        GASubscript(Name("Literal"), [Name("int")]),
                    ],
                )
            )
            == "Dict[Union[int, str], None, Literal[int]]"
        )
        assert (
            repr(
                UnionType(
                    [
                        GASubscript(TypingName("ttt", "List"), [Name("int")]),
                        GASubscript(TypingName("ttt", "Tuple"), [Name("int")]),
                        GASubscript(TypingName("ttt", "Set"), [Name("int")]),
                        GASubscript(
                            TypingName("ttt", "Dict"), [Name("str"), Name("int")]
                        ),
                        GASubscript(TypingName("ttt", "FrozenSet"), [Name("int")]),
                        GASubscript(TypingName("ttt", "Type"), [Name("int")]),
                    ]
                )
            )
            == "list[int] | tuple[int] | set[int] | dict[str, int] | frozenset[int] | type[int]"
        )
        assert repr(UnionType([Name("str"), None])) == "str | None"
        assert repr(CallableType(..., Name("str"))) == "(...) -> str"
        assert (
            repr(
                CallableType(
                    [Name("int"), Name("str")],
                    CallableType([Name("str")], CallableType([], None)),
                )
            )
            == "(int, str) -> (str) -> () -> None"
        )
        assert (
            repr(
                UnionType(
                    [
                        CallableType([], UnionType([Name("str"), None])),
                        Name("str"),
                        None,
                    ]
                )
            )
            == "() -> (str | None) | str | None"
        )


class TestAnnotation:
    def test_is_typealias(self):
        anncontext = _AnnContext(["t"], {})
        ann = Annotation(get_expr("t.TypeAlias"), anncontext)
        assert ann.is_typealias

    def test_is_classvar(self):
        anncontext = _AnnContext(["t"], {})
        ann = Annotation(get_expr("t.ClassVar[int]"), anncontext)
        assert ann.is_classvar
