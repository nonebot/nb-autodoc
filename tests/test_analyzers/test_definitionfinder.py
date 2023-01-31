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
        visitor = DefinitionFinder(package="mypkg.pkg.pkg", source=code)
        visitor.visit(module)
        del code, module
        # duplicated from repr
        # notice that AssignData.annotation is uncomparable `ast.Expression`
        # so until unparser implement (maybe py3.8), annotation test is unavailable
        assert visitor.module.scope == {
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
        visitor = DefinitionFinder(package="<test>", source=code)
        visitor.visit(module)
        assert visitor.module.scope == {
            "a": AssignData(
                order=0, name="a", type_comment=None, docstring="a first docstring"
            ),
            "b": AssignData(
                order=1, name="b", type_comment=None, docstring="b first docstring"
            ),
        }
        assert isinstance(visitor.module.scope["b"].annotation, ast.Name)

    def test_type_checking(self):
        code = get_analyzer_data("type-checking-ast.py")
        module = ast_parse(code)
        visitor = DefinitionFinder(package="<test>", source=code)
        visitor.visit(module)
        assert visitor.module.scope == {
            "TYPE_CHECKING": ImportFromData(
                0, "TYPE_CHECKING", "typing", "TYPE_CHECKING"
            ),
            "A": ImportFromData(1, "A", "mypkg", "A"),
            "A_": ClassDefData(2, "A_"),
            "a": FunctionDefData(3, "a"),
            "B": ClassDefData(
                4,
                "B",
                scope={
                    "f": ImportFromData(5, "f", "mypkg", "f"),
                    "B_": ClassDefData(6, "B_"),
                    "B__": ClassDefData(7, "B__"),
                    "f2": ImportFromData(8, "f2", "mypkg", "f2"),
                },
            ),
        }
        tc_classes = [i.__class__ for i in visitor.module.type_checking_body]
        assert tc_classes == [ast.ImportFrom, ast.ClassDef]
        tc_classes = [i.__class__ for i in visitor.module.scope["B"].type_checking_body]
        assert tc_classes == [ast.ImportFrom, ast.ClassDef, ast.If, ast.ImportFrom]

    def test_overload(self):
        code = get_analyzer_data("overload.py")
        module = ast_parse(code)
        visitor = DefinitionFinder(package="<test>", source=code)
        visitor.visit(module)
        func = visitor.module.scope["func"]
        func2 = visitor.module.scope["func2"]
        assert func.__class__ is FunctionDefData
        assert len(func.overloads) == 2
        assert func.overloads[0].docstring == "func o1"
        assert func.overloads[1].docstring == "func o2"
        assert func.signature
        assert func2.__class__ is FunctionDefData
        assert len(func2.overloads) == 2
        assert not func2.signature
        assert func2.assign_docstring == "func2 docstring"
