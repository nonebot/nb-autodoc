import ast
import pathlib
import re
import sys
from pathlib import Path

import pytest

from nb_autodoc.analyzer import Analyzer, VariableVisitor, ast_parse, convert_annot

from .data import example_google_docstring as egd


@pytest.fixture(scope="module")
def example_ast_module():
    file = Path(__file__).resolve().parent / "data" / "example_google_docstring.py"
    return ast_parse(open(file, "r").read())


lines = open(
    Path(__file__).parent / "data" / "no-import" / "ast_code_with_marker.py"
).readlines()


def get_code_by_marker(marker: str) -> str:
    marker_re = re.compile(rf"# autodoc: {marker} on")
    end_marker_re = re.compile(rf"# autodoc: {marker} off")
    for i, line in enumerate(lines):
        if marker_re.match(line):
            lineno = i
    for i in range(lineno, len(lines[lineno:])):  # type: ignore
        if end_marker_re.match(lines[i]):
            end_lineno = i
    return "".join(lines[lineno:end_lineno])  # type: ignore


def node_to_dict(node: ast.AST) -> dict:
    ...


def test_Analyzer():
    analyzer = Analyzer(
        "tests.data.stuff1", "tests.data", Path(__file__).parent / "data" / "stuff1.py"
    )
    target = {
        "re": re,
        "MyPath": pathlib.Path,
        "MyPurePath": pathlib.PurePath,
        "egd": egd,
        "ec": egd.ExampleClass,
    }
    assert "tests.data.stuff1" not in sys.modules
    assert {k: analyzer.globalns[k] for k in target} == target
    assert analyzer.globalns["A"].__module__ == "tests.data.stuff1"


def test_VariableVisitor():
    code = get_code_by_marker("test_VariableVisitor")
    module = ast_parse(code)
    visitor = VariableVisitor()
    visitor.visit(module)
    # Duplicated from debug
    docstrings = {
        "a": "a docstring",
        "b": "b docstring",
        "c": "c and d docstring",
        "d": "c and d docstring",
        "a1": "abcde11111 docstring",
        "b1": "abcde11111 docstring",
        "c1": "abcde11111 docstring",
        "d1": "abcde11111 docstring",
        "e1": "abcde11111 docstring",
        "B.a": "B.a docstring",
        "C.a": "C.a docstring",
        "C.__init__.a": "C.__init__.a/b docstring",
        "C.__init__.b": "C.__init__.a/b docstring",
        "C.__init__.d": "C.__init__.d docstring",
    }
    assert visitor.comments == docstrings
    if sys.version_info >= (3, 8):
        assert visitor.type_comments == {
            "a": "int>>invalid",
            "b": "int",
            "C.__init__.a": "str | None",
            "C.__init__.b": "str | None",
        }
    annotations = {
        k: ast.get_source_segment(code, v) for k, v in visitor.annotations.items()
    }
    assert annotations == {"C.__init__.c": "int", "C.__init__.d": "str"}


def test_convert_annot():
    assert (
        convert_annot("Union[List[int], Tuple[int], Set[int], Dict[str, int]]")
        == "list[int] | tuple[int] | set[int] | dict[str, int]"
    )
    assert convert_annot("Optional[str]") == "str | None"
    assert convert_annot("Callable[..., str]") == "(*Any, **Any) -> str"
    assert (
        convert_annot("Callable[[int, str], Callable[[str], Callable[[], None]]]")
        == "(int, str) -> (str) -> () -> None"
    )
    assert (
        convert_annot("Union[Callable[[], Optional[str]], str, None]")
        == "() -> (str | None) | str | None"
    )
