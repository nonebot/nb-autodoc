from nb_autodoc.docstringparser.google import GoogleStyleParser
from nb_autodoc.nodes import Args, ColonArg, Docstring, Returns, Role, Text, Raises
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
            descr="descr long descr",
            long_descr="",
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
            descr="descr long descr",
            long_descr="",
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

    def test_combined_colonarg_short_description(self):
        parse = lambda doc: GoogleStyleParser(doc).parse()
        doc = cleandoc(
            """
            Args:
                arg: short
                    short descr.
                arg2: short
                    short descr.

                    long
                    long descr.
                arg3: short descr.

                    long descr.
            Raises:
                ValueError: short
                    short descr.

                    long
                    long descr.
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
                            name="arg",
                            annotation=None,
                            roles=[],
                            descr="short short descr.",
                            long_descr="",
                        ),
                        ColonArg(
                            name="arg2",
                            annotation=None,
                            roles=[],
                            descr="short short descr.",
                            long_descr="long\nlong descr.",
                        ),
                        ColonArg(
                            name="arg3",
                            annotation=None,
                            roles=[],
                            descr="short descr.",
                            long_descr="long descr.",
                        ),
                    ],
                    vararg=None,
                    kwonlyargs=[],
                    kwarg=None,
                ),
                Raises(
                    name="Raises",
                    args=[
                        ColonArg(
                            name=None,
                            annotation="ValueError",
                            roles=[],
                            descr="short short descr.",
                            long_descr="long\nlong descr.",
                        )
                    ],
                ),
            ],
        )
