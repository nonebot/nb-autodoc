import ast
import pathlib
import re
import sys
from pathlib import Path

import pytest

from .data import example_google_docstring as egd

lines = open(
    Path(__file__).parent / "data" / "no-import" / "ast_code_with_marker.py"
).readlines()


def get_code_by_marker(marker: str) -> str:
    marker_re = re.compile(rf"# autodoc: {marker} on")
    end_marker_re = re.compile(rf"# autodoc: {marker} off")
    for i, line in enumerate(lines):
        if marker_re.match(line):
            lineno = i
    for i in range(lineno, len(lines)):  # type: ignore
        if end_marker_re.match(lines[i]):
            end_lineno = i
    return "".join(lines[lineno:end_lineno])  # type: ignore


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


def test_DefinitionFinder():
    code = get_code_by_marker("test_DefinitionFinder")
    module = ast_parse(code)
    visitor = DefinitionFinder("mypkg.pkg", "mypkg.pkg.pkg")
    visitor.visit(module)
    del code, module
    print(visitor.deforders)
    assert visitor.deforders == {
        "ext_B": 0,
        "ext_fb": 1,
        "ext_fc": 2,
        "a": 7,
        "a2": 4,
        "a3": 5,
        "b": 6,
        "c": 8,
        "d": 9,
        "a1": 10,
        "b1": 11,
        "c1": 12,
        "d1": 13,
        "e1": 14,
        "A": 15,
        "A.a": 16,
        "B": 17,
        "B.a": 18,
        "B1": 19,
        "B1.a": 20,
        "B1.__init__": 21,
        "B1.b": 22,
        "C": 23,
        "C.a": 24,
        "C.ma": 25,
        "C.__init__": 26,
        "C.__init__.a": 27,
        "C.__init__.b": 28,
        "C.__init__.c": 29,
        "C.__init__.d": 30,
        "C._A": 31,
    }
    print(visitor.deforders)
    _target_comments = {
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
    assert visitor.comments == _target_comments
    if sys.version_info >= (3, 8):
        _type_comments = {k: ast.unparse(v) for k, v in visitor.type_comments.items()}
        assert _type_comments == {
            "a": "'int'",
            "a2": "'int'",
            "b": "'int'",
            "C.__init__.a": "'str | None'",
            "C.__init__.b": "'str | None'",
        }
    _annotations = {k: ast.unparse(v) for k, v in visitor.annotations.items()}
    assert _annotations == {"a3": "'A'", "C.__init__.c": "int", "C.__init__.d": "str"}
    assert visitor.externals == {
        "ext_B": "mypkg.pkg.ext_B",
        "ext_fb": "mypkg.pkg.ext_fb",
        "ext_fc": "mypkg.pkg.pkg.util.ext_fc",
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
