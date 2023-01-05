import ast

from nb_autodoc.analyzers.analyzer import Analyzer
from nb_autodoc.utils import TypeCheckingClass

_fix = ast.fix_missing_locations


def is_dunder(s: str) -> bool:
    return s.startswith("__") and s.endswith("__")


def get_non_dunder_names(names):
    return {i for i in names if not is_dunder(i)}


class TestAnalyzer:
    def test_exec_type_checking_simple(self):
        analyzer = Analyzer("<test>", "<test>", "<test>")
        globals = {}
        simple_assign = _fix(
            ast.Assign(targets=[ast.Name("a", ctx=ast.Store())], value=ast.Str("value"))
        )
        analyzer._exec_stub_safe(
            [simple_assign],
            globals,
        )
        assert {"a"} == get_non_dunder_names(globals.keys())
        globals = {}
        locals = {}
        analyzer._exec_stub_safe([simple_assign], globals, locals)
        assert not get_non_dunder_names(globals.keys())
        assert {"a"} == get_non_dunder_names(locals.keys())

        from tests.analyzerdata import exec_type_checking as module

        analyzer = Analyzer("<test>", "<package>", module.__file__)
        analyzer.analyze()
        locals = {}
        preexec_names = tuple(module.__dict__.items())
        analyzer._exec_stub_safe(
            analyzer.module.type_checking_body, module.__dict__, locals
        )
        assert preexec_names == tuple(module.__dict__.items())
        assert isinstance(locals["ModuleManager"], type)
        assert issubclass(locals["Logger"], TypeCheckingClass)
        assert locals["b"] == 1
        assert locals["func"].__annotations__["return"] == "X | Y"
