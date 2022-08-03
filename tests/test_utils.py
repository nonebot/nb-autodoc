import ast
import inspect
import textwrap
from pathlib import Path
from typing import List, Union, cast

import pytest

from nb_autodoc.utils import cleandoc, dedent


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


@pytest.fixture
def docstrings():
    file = Path(__file__).resolve().parent / "data" / "example_google_docstring.py"
    docstrings = traverse_docstring(file)
    return docstrings


@pytest.fixture
def docstrings_no_firstline(docstrings: List[str]) -> List[str]:
    results = []
    for docstring in docstrings:
        chunk = docstring.split("\n", 1)
        if len(chunk) == 1:
            continue
        results.append(chunk[1])
    return results


def listrun(f, docstrings):
    results = []
    for d in docstrings:
        results.append(f(d))
    return results


@pytest.mark.benchmark(group="utils.dedent")
def test_dedent(benchmark, docstrings_no_firstline: List[str]) -> None:
    benchmark.pedantic(
        listrun, (dedent, docstrings_no_firstline), iterations=10, rounds=1000
    )
    for text in docstrings_no_firstline:
        test_text = dedent(text)[1]
        target_text = textwrap.dedent(text)
        assert test_text == target_text


@pytest.mark.benchmark(group="utils.dedent")
def test_textwrap_dedent(benchmark, docstrings_no_firstline: List[str]) -> None:
    benchmark.pedantic(
        listrun, (textwrap.dedent, docstrings_no_firstline), iterations=10, rounds=1000
    )


@pytest.mark.benchmark(group="utils.cleandoc")
def test_cleandoc(benchmark, docstrings: List[str]) -> None:
    benchmark.pedantic(listrun, (cleandoc, docstrings), iterations=10, rounds=1000)
    for docstring in docstrings:
        test_docstring = cleandoc(docstring)
        target_docstring = inspect.cleandoc(docstring)
        assert test_docstring == target_docstring


@pytest.mark.benchmark(group="utils.cleandoc")
def test_inspect_cleandoc(benchmark, docstrings: List[str]) -> None:
    benchmark.pedantic(
        listrun, (inspect.cleandoc, docstrings), iterations=10, rounds=1000
    )
