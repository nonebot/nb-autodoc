from nb_autodoc.docstringparser.google import GoogleStyleParser
from nb_autodoc.nodes import Args, ColonArg, Docstring, Returns, Role, Text
from nb_autodoc.utils import cleandoc


class TestGoogleStyleParser:
    def test_parse_common(self):
        parse = lambda doc: GoogleStyleParser(doc).parse()
        assert parse(" ") == Docstring(
            roles=[], annotation=None, descr="", long_descr="", sections=[]
        )
        assert parse("description") == Docstring(
            roles=[], annotation=None, descr="description", long_descr="", sections=[]
        )
        assert parse("Union[int, str]: description") == Docstring(
            roles=[],
            annotation="Union[int, str]",
            descr="description",
            long_descr="",
            sections=[],
        )
        assert parse("int: descr\nlong descr") == Docstring(
            roles=[],
            annotation="int",
            descr="descr",
            long_descr="long descr",
            sections=[],
        )
        assert parse("{ver}`1.1.0+` descr") == Docstring(
            roles=[Role("ver", None, "1.1.0+")],
            annotation=None,
            descr="descr",
            long_descr="",
            sections=[],
        )
        assert parse("{ver}`1.1.0+`\ndescr") == Docstring(
            roles=[Role("ver", None, "1.1.0+")],
            annotation=None,
            descr="descr",
            long_descr="",
            sections=[],
        )
        assert parse("{ver}`1.1.0+` Union[int, str]: descr") == Docstring(
            roles=[Role("ver", None, "1.1.0+")],
            annotation="Union[int, str]",
            descr="descr",
            long_descr="",
            sections=[],
        )
        assert parse("{ver}`1.1.0+` Union[int, str]: descr\nlong descr") == Docstring(
            roles=[Role("ver", None, "1.1.0+")],
            annotation="Union[int, str]",
            descr="descr",
            long_descr="long descr",
            sections=[],
        )
        assert parse(
            "{ver}`1.1.0+` Union[int, str]: descr\n\nlong descr\n\nlong long descr"
        ) == Docstring(
            roles=[Role("ver", None, "1.1.0+")],
            annotation="Union[int, str]",
            descr="descr",
            long_descr="long descr\n\nlong long descr",
            sections=[],
        )
        doc = cleandoc(
            """
            Args:
                a: descr
            """
        )
        assert parse(doc) == Docstring(
            roles=[],
            annotation=None,
            descr="",
            long_descr="",
            sections=[
                Args(
                    name="Args",
                    args=[
                        ColonArg(
                            name="a",
                            annotation=None,
                            roles=[],
                            descr="descr",
                            long_descr="",
                        )
                    ],
                    vararg=None,
                    kwonlyargs=[],
                    kwarg=None,
                )
            ],
        )
        doc = cleandoc(
            """description.
            Args:
                a: descr
            """
        )
        assert parse(doc) == Docstring(
            roles=[],
            annotation=None,
            descr="description.",
            long_descr="",
            sections=[
                Args(
                    name="Args",
                    args=[
                        ColonArg(
                            name="a",
                            annotation=None,
                            roles=[],
                            descr="descr",
                            long_descr="",
                        )
                    ],
                    vararg=None,
                    kwonlyargs=[],
                    kwarg=None,
                )
            ],
        )
        doc = cleandoc(
            """description.

            Args:
                a: descr

            :::tip
            any text between two section
            :::

            返回:
                Union[int, str]: descr
            """
        )
        assert parse(doc) == Docstring(
            roles=[],
            annotation=None,
            descr="description.",
            long_descr="",
            sections=[
                Args(
                    name="Args",
                    args=[
                        ColonArg(
                            name="a",
                            annotation=None,
                            roles=[],
                            descr="descr",
                            long_descr="",
                        )
                    ],
                    vararg=None,
                    kwonlyargs=[],
                    kwarg=None,
                ),
                Text(value=":::tip\nany text between two section\n:::"),
                Returns(
                    name="返回",
                    version=None,
                    value=ColonArg(
                        name=None,
                        annotation="Union[int, str]",
                        roles=[],
                        descr="descr",
                        long_descr="",
                    ),
                ),
            ],
        )
