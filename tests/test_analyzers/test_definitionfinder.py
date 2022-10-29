import ast
from pathlib import Path

from nb_autodoc.analyzers.definitionfinder import (
    AssignData,
    ClassDefData,
    DefinitionFinder,
    FunctionDefData,
)
from nb_autodoc.analyzers.utils import ast_parse


def get_analyzer_data(filename: str) -> str:
    return open(Path(__file__).parent / "analyzerdata" / filename).read()


class TestDefinitionFinder:
    def test_simple_data(self):
        code = get_analyzer_data("simple-definition-ast.py")
        module = ast_parse(code)
        visitor = DefinitionFinder("mypkg.pkg", "mypkg.pkg.pkg")
        visitor.visit(module)
        del code, module
        module_freevars = visitor.freevars
        # duplicated from repr(module_freevars)
        # notice that AssignData.annotation is uncomparable `ast.Expression`
        # so until unparser implement (maybe py3.8), annotation test is unavailable
        assert module_freevars == {
            "a": AssignData(
                order=0, name="a", type_comment="int", docstring="a docstring"
            ),
            "a2": AssignData(order=1, name="a2", type_comment="int", docstring=None),
            "a3": AssignData(order=2, name="a3", type_comment=None, docstring=None),
            "b": AssignData(
                order=3, name="b", type_comment="int", docstring="b docstring"
            ),
            "fa": FunctionDefData(order=4, name="fa"),
            "c": AssignData(
                order=5, name="c", type_comment=None, docstring="c and d docstring"
            ),
            "d": AssignData(
                order=6, name="d", type_comment=None, docstring="c and d docstring"
            ),
            "a1": AssignData(
                order=7, name="a1", type_comment=None, docstring="abcde11111 docstring"
            ),
            "b1": AssignData(
                order=8, name="b1", type_comment=None, docstring="abcde11111 docstring"
            ),
            "c1": AssignData(
                order=9, name="c1", type_comment=None, docstring="abcde11111 docstring"
            ),
            "d1": AssignData(
                order=10, name="d1", type_comment=None, docstring="abcde11111 docstring"
            ),
            "e1": AssignData(
                order=11, name="e1", type_comment=None, docstring="abcde11111 docstring"
            ),
            "A": ClassDefData(
                order=12,
                name="A",
                freevars={
                    "a": AssignData(
                        order=13, name="a", type_comment=None, docstring=None
                    )
                },
                instance_vars={},
                methods={},
            ),
            "B": ClassDefData(
                order=14,
                name="B",
                freevars={
                    "a": AssignData(
                        order=15, name="a", type_comment=None, docstring="B.a docstring"
                    )
                },
                instance_vars={},
                methods={},
            ),
            "B1": ClassDefData(
                order=16,
                name="B1",
                freevars={
                    "a": AssignData(
                        order=17, name="a", type_comment=None, docstring=None
                    ),
                    "__init__": FunctionDefData(order=18, name="__init__"),
                    "b": FunctionDefData(order=19, name="b"),
                },
                instance_vars={},
                methods={},
            ),
            "C": ClassDefData(
                order=20,
                name="C",
                freevars={
                    "a": AssignData(
                        order=21,
                        name="a",
                        type_comment=None,
                        docstring="C.a classvar docstring",
                    ),
                    "__init__": FunctionDefData(order=22, name="__init__"),
                    "_A": ClassDefData(
                        order=27,
                        name="_A",
                        freevars={
                            "_a": AssignData(
                                order=28,
                                name="_a",
                                type_comment=None,
                                docstring="nested OK",
                            )
                        },
                        instance_vars={},
                        methods={},
                    ),
                },
                instance_vars={
                    "a": AssignData(
                        order=23,
                        name="a",
                        type_comment="int | None",
                        docstring="C instance var a/b docstring",
                    ),
                    "b": AssignData(
                        order=24,
                        name="b",
                        type_comment="int | None",
                        docstring="C instance var a/b docstring",
                    ),
                    "c": AssignData(
                        order=25, name="c", type_comment=None, docstring=None
                    ),
                    "d": AssignData(
                        order=26,
                        name="d",
                        type_comment=None,
                        docstring="C instance var d docstring",
                    ),
                },
                methods={},
            ),
        }

    def test_assigndata_override(self):
        code = get_analyzer_data("assigndata-override-ast.py")
        module = ast_parse(code)
        visitor = DefinitionFinder("<test>", "<test>")
        visitor.visit(module)
        module_freevars = visitor.freevars
        assert module_freevars == {
            "a": AssignData(
                order=0, name="a", type_comment=None, docstring="a first docstring"
            ),
            "b": AssignData(
                order=1, name="b", type_comment=None, docstring="b first docstring"
            ),
        }
        assert isinstance(module_freevars["b"].annotation.body, ast.Name)
