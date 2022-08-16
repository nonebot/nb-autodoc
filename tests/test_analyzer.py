import pathlib
import re
import sys
from pathlib import Path

import pytest

from nb_autodoc.analyzer import (
    Analyzer,
    AssignData,
    ast_parse,
    convert_annot,
    traverse_assign,
)

from .data import example_google_docstring as egd


@pytest.fixture(scope="module")
def example_ast_module():
    file = Path(__file__).resolve().parent / "data" / "example_google_docstring.py"
    return ast_parse(open(file, "r").read())


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


code = '''
a = 1  # type: int>>invalid
"""a docstring"""
b = 2  # type: int
"""b docstring"""
"""bad"""
def a(): ...
"""bad"""
c = d = 3
"""c and d docstring"""
x['_'], x.attr = 1, 2
"""bad"""

x['_'], (a, b) = c, (d, e) = 1, (2, 3)
"""abcde docstring"""
'''


def test_traverse_assign():
    module = ast_parse(code)
    res = traverse_assign(module)
    assert res == {
        ("a",): AssignData("a docstring", "int>>invalid"),
        ("b",): AssignData("b docstring", "int"),
        ("c", "d"): AssignData("c and d docstring", None),
        (): AssignData("bad", None),
        ("a", "b", "c", "d", "e"): AssignData("abcde docstring", None),
    }


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
