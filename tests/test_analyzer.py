import pathlib
import re
from pathlib import Path

from nb_autodoc.analyzer import Analyzer, convert_annot

from .data import example_google_docstring as egd


def test_Analyzer():
    analyzer = Analyzer(
        Path(__file__).parent / "data" / "stuff1.py", package="tests.data"
    )
    assert analyzer.type_checking_imports == {
        "re": re,
        "MyPath": pathlib.Path,
        "MyPurePath": pathlib.PurePath,
        "egd": egd,
        "ec": egd.ExampleClass,
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
