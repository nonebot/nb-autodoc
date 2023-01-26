import ast
import inspect
import os
import textwrap
from functools import partial
from pathlib import Path
from typing import Callable, List, TypeVar, Union, cast

import pytest

from nb_autodoc.utils import cleandoc, dedent, getmodulename, stringify_signature

T = TypeVar("T")
TT = TypeVar("TT")


def _is_str_node(node: ast.Expr) -> bool:
    import sys

    node = node.value  # type: ignore

    if sys.version_info >= (3, 8):
        return isinstance(node, ast.Constant) and isinstance(node.s, str)
    return isinstance(node, ast.Str)


def _compat_get_text(node: ast.Expr) -> str:
    # input must be checked as string node
    return getattr(node.value, node.value._fields[0])


def _traverse_docstring(node: Union[ast.Module, ast.ClassDef]) -> List[str]:
    docstrings: List[str] = []

    stmt = node.body[0]
    if isinstance(stmt, ast.Expr) and _is_str_node(stmt):
        docstrings.append(_compat_get_text(stmt))

    for i, stmt in enumerate(node.body):
        if (
            isinstance(stmt, (ast.Assign, ast.AnnAssign))
            and (not i == len(node.body))
            and isinstance(node.body[i + 1], ast.Expr)
        ):
            expr = cast("ast.Expr", node.body[i + 1])
            if not _is_str_node(expr):
                continue
            docstrings.append(_compat_get_text(expr))
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and isinstance(
            stmt.body[0], ast.Expr
        ):
            expr = stmt.body[0]
            if not _is_str_node(expr):
                continue
            docstrings.append(_compat_get_text(expr))
        elif isinstance(stmt, ast.ClassDef):
            docstrings.extend(_traverse_docstring(stmt))

    return docstrings


def traverse_docstring(module_file: Union[Path, str]) -> List[str]:
    """Traverse docstring by analysis AST.

    Simply traverse the top-level variable, function, class, method docstring.

    Class variable assign (or annotation) (not __init__) can be detected normally,
    even though this is not experimented.

    There is more trouble using import system, such as variable docstring.
    """
    mod = ast.parse(open(module_file, "r").read())
    docstrings = _traverse_docstring(mod)
    return docstrings


@pytest.fixture(scope="module")
def docstrings():
    file = Path(__file__).resolve().parent / "data" / "example_google_docstring.py"
    docstrings = traverse_docstring(file)
    return docstrings


@pytest.fixture(scope="module")
def indented_texts(docstrings: List[str]):
    results = []
    for docstring in docstrings:
        chunk = docstring.split("\n", 1)
        if len(chunk) == 1:
            continue
        results.append(chunk[1])
    return results


# inspect


def test_getmodulename():
    norm = os.path.normpath
    assert getmodulename(norm("/home/user/xxx.py")) == "xxx"
    assert getmodulename(norm("__init__.py")) == "__init__"
    assert getmodulename(norm("./__init__.so")) == "__init__"
    assert getmodulename(norm("/xxx.pyi")) == None
    assert getmodulename(norm("/xxx-yyy.py")) == None


def test_stringify_signature():
    def func(a: int, b: dict = {}) -> str:
        ...

    sig = inspect.signature(func)
    assert stringify_signature(sig) == "(a, b={})"
    assert (
        stringify_signature(sig, replace_ann=False, show_returns=True)
        == "(a: int, b: dict = {}) -> str"
    )


# def test_formatannotation():
#     class Foo:
#         ...

#     Foo.__module__ = "test.typing"
#     Foo.__qualname__ = "Foo"

#     assets = {
#         None: "None",
#         "AnyStr": "AnyStr",
#         List[int]: "List[int]",
#         Union[int, None]: "Optional[int]",
#         Tuple[int, ...]: "Tuple[int, ...]",
#         Dict[str, None]: "Dict[str, None]",
#         Callable[
#             [int, "Fake", Foo], "Fake"
#         ]: "Callable[[int, Fake, test.typing.Foo], Fake]",
#         Union[int, "Fake"]: "Union[int, Fake]",  # Warning unevaluated ForwardRef
#         NewType("Fake", int): "Fake",
#         (
#             Dict[Union[int, str], Callable[..., str]]
#         ): "Dict[Union[int, str], Callable[..., str]]",
#         ForwardRef("Fake"): "Fake",
#     }
#     if sys.version_info >= (3, 9):
#         assets.update({Annotated[int, list, "any"]: "int"})
#         # types.GenericAlias has no arg check
#         assets.update(
#             {
#                 list[Foo, "Fake"]: "list[test.typing.Foo, Fake]",
#                 Union[int, list[int, "Fake"]]: "Union[int, list[int, Fake]]",
#                 list[int, Union[int, str], str]: "list[int, Union[int, str], str]",
#             }
#         )
#     with pytest.raises(TypeError):
#         formatannotation(..., {})
#     for annot, text in assets.items():
#         assert formatannotation(annot, {}) == text


def partial_map(f: Callable[[T], TT], lst: List[T]) -> Callable[[], List[TT]]:
    return partial(list, map(f, lst))


@pytest.mark.benchmark(group="utils.dedent")
def test_dedent(indented_texts: List[str]):
    # benchmark.pedantic(partial_map(dedent, indented_texts), iterations=10, rounds=100)
    for text in indented_texts:  # for string diff
        test_text = dedent(text)
        target_text = textwrap.dedent(text)
        assert test_text == target_text


# @pytest.mark.benchmark(group="utils.dedent")
# def test_textwrap_dedent(benchmark, indented_texts: List[str]):
#     benchmark.pedantic(
#         partial_map(textwrap.dedent, indented_texts), iterations=10, rounds=100
#     )


@pytest.mark.benchmark(group="utils.cleandoc")
def test_cleandoc(docstrings: List[str]):
    # benchmark.pedantic(partial_map(cleandoc, docstrings), iterations=10, rounds=100)
    for docstring in docstrings:
        test_docstring = cleandoc(docstring)
        target_docstring = inspect.cleandoc(docstring)
        assert test_docstring == target_docstring


# @pytest.mark.benchmark(group="utils.cleandoc")
# def test_inspect_cleandoc(benchmark, docstrings: List[str]):
#     benchmark.pedantic(
#         partial_map(inspect.cleandoc, docstrings), iterations=10, rounds=100
#     )
