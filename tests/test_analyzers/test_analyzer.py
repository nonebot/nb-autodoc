import ast

from nb_autodoc.analyzers.analyzer import Analyzer
from nb_autodoc.utils import TypeCheckingClass


class TestAnalyzer:
    def test_exec_type_checking_simple(self):
        analyzer = Analyzer("<test>", "<test>", "<test>")
        globals = {}
        simple_assign = ast.Assign(
            targets=[ast.Name("a", ctx=ast.Store())], value=ast.Str("value")
        )
        analyzer.exec_type_checking_body(
            [simple_assign],
            globals,
        )
        assert "a" in globals.keys()
        globals = {}
        locals = {}
        analyzer.exec_type_checking_body([simple_assign], globals, locals)
        assert "a" not in globals.keys()
        assert "a" in locals.keys()

        from tests.analyzerdata import exec_type_checking as module

        analyzer = Analyzer("<test>", "<package>", module.__file__)
        analyzer.analyze()
        locals = {}
        analyzer.exec_type_checking_body(
            analyzer.module.type_checking_body, module.__dict__, locals
        )
        assert all(
            i.startswith("__") for i in module.__dict__.keys() - {"TYPE_CHECKING", "a"}
        )
        assert isinstance(locals["ModuleManager"], type)
        assert issubclass(locals["Logger"], TypeCheckingClass)
        assert locals["b"] == 1
        assert locals["func"].__annotations__["return"] == "X | Y"
