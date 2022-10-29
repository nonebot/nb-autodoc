import ast
from pathlib import Path

from nb_autodoc.analyzers.definitionfinder import (
    AssignData,
    ClassDefData,
    DefinitionFinder,
    FunctionDefData,
    ImportFromData,
)
from nb_autodoc.analyzers.utils import ast_parse


def get_analyzer_data(filename: str) -> str:
    return open(Path(__file__).parent.parent / "analyzerdata" / filename).read()


class TestDefinitionFinder:
    def test_simple_data(self):
        code = get_analyzer_data("simple-definition-ast.py")
        module = ast_parse(code)
        visitor = DefinitionFinder(package="mypkg.pkg.pkg")
        visitor.visit(module)
        del code, module
        module_freevars = visitor.scope
        # duplicated from repr(module_freevars)
        # notice that AssignData.annotation is uncomparable `ast.Expression`
        # so until unparser implement (maybe py3.8), annotation test is unavailable
        assert module_freevars == {
            "Path_rename": ImportFromData(
                order=0, name="Path_rename", module="pathlib", orig_name="Path"
            ),
            "ext_A_rename": ImportFromData(
                order=1, name="ext_A_rename", module="mypkg", orig_name="ext_A"
            ),
            "ext_fa": ImportFromData(
                order=2, name="ext_fa", module="mypkg", orig_name="ext_fa"
            ),
            "ext_B": ImportFromData(
                order=3, name="ext_B", module="mypkg.pkg", orig_name="ext_B"
            ),
            "ext_fb": ImportFromData(
                order=4, name="ext_fb", module="mypkg.pkg", orig_name="ext_fb"
            ),
            "ext_fc": ImportFromData(
                order=5, name="ext_fc", module="mypkg.pkg.pkg.util", orig_name="ext_fc"
            ),
            "a": AssignData(
                order=6, name="a", type_comment="int", docstring="a docstring"
            ),
            "a2": AssignData(order=7, name="a2", type_comment="int", docstring=None),
            "a3": AssignData(order=8, name="a3", type_comment=None, docstring=None),
            "b": AssignData(
                order=9, name="b", type_comment="int", docstring="b docstring"
            ),
            "fa": FunctionDefData(order=10, name="fa"),
            "c": AssignData(
                order=11, name="c", type_comment=None, docstring="c and d docstring"
            ),
            "d": AssignData(
                order=12, name="d", type_comment=None, docstring="c and d docstring"
            ),
            "a1": AssignData(
                order=13, name="a1", type_comment=None, docstring="abcde11111 docstring"
            ),
            "b1": AssignData(
                order=14, name="b1", type_comment=None, docstring="abcde11111 docstring"
            ),
            "c1": AssignData(
                order=15, name="c1", type_comment=None, docstring="abcde11111 docstring"
            ),
            "d1": AssignData(
                order=16, name="d1", type_comment=None, docstring="abcde11111 docstring"
            ),
            "e1": AssignData(
                order=17, name="e1", type_comment=None, docstring="abcde11111 docstring"
            ),
            "A": ClassDefData(
                order=18,
                name="A",
                scope={
                    "a": AssignData(
                        order=19, name="a", type_comment=None, docstring=None
                    )
                },
                instance_vars={},
                methods={},
            ),
            "B": ClassDefData(
                order=20,
                name="B",
                scope={
                    "a": AssignData(
                        order=21, name="a", type_comment=None, docstring="B.a docstring"
                    )
                },
                instance_vars={},
                methods={},
            ),
            "B1": ClassDefData(
                order=22,
                name="B1",
                scope={
                    "a": AssignData(
                        order=23, name="a", type_comment=None, docstring=None
                    ),
                    "__init__": FunctionDefData(order=24, name="__init__"),
                    "b": FunctionDefData(order=25, name="b"),
                },
                instance_vars={},
                methods={},
            ),
            "C": ClassDefData(
                order=26,
                name="C",
                scope={
                    "a": AssignData(
                        order=27,
                        name="a",
                        type_comment=None,
                        docstring="C.a classvar docstring",
                    ),
                    "__init__": FunctionDefData(order=28, name="__init__"),
                    "_A": ClassDefData(
                        order=33,
                        name="_A",
                        scope={
                            "_a": AssignData(
                                order=34,
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
                        order=29,
                        name="a",
                        type_comment="int | None",
                        docstring="C instance var a/b docstring",
                    ),
                    "b": AssignData(
                        order=30,
                        name="b",
                        type_comment="int | None",
                        docstring="C instance var a/b docstring",
                    ),
                    "c": AssignData(
                        order=31, name="c", type_comment=None, docstring=None
                    ),
                    "d": AssignData(
                        order=32,
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
        visitor = DefinitionFinder(package="<test>")
        visitor.visit(module)
        module_freevars = visitor.scope
        assert module_freevars == {
            "a": AssignData(
                order=0, name="a", type_comment=None, docstring="a first docstring"
            ),
            "b": AssignData(
                order=1, name="b", type_comment=None, docstring="b first docstring"
            ),
        }
        assert isinstance(module_freevars["b"].annotation.body, ast.Name)
