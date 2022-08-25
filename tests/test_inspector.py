from typing import Dict, Set, Tuple, Type, TypeVar

import pytest

from nb_autodoc.inspector import External, LibraryAttr, ModuleManager
from nb_autodoc.typing import T_ModuleMember

T = TypeVar("T")


@pytest.fixture(scope="module")
def main_modulemanager():
    return ModuleManager("tests.test_pkg")


def flat_external(dct: Dict[str, External]) -> Dict[str, str]:
    return {k: v.refname for k, v in dct.items()}


def flat_libraryattr(dct: Dict[str, LibraryAttr]) -> Dict[str, Tuple[str, str]]:
    return {k: (v.docname, v.docstring) for k, v in dct.items()}


def filter_type(dct: Dict[str, T_ModuleMember], typ: Type[T]) -> Dict[str, T]:
    return {k: v for k, v in dct.items() if isinstance(v, typ)}


def filter_spec_module_prefix(st: Set[str], prefix: str) -> Set[str]:
    return {s for s in st if s.startswith(prefix + ".")}


def test_resolve_autodoc():
    manager = ModuleManager("tests.test_pkg.sub")
    test_module = manager.modules["tests.test_pkg.sub"]
    assert test_module.is_package
    assert filter_spec_module_prefix(
        manager.context.blacklist, "tests.test_pkg.sub._reexport_sample"
    ) == {"tests.test_pkg.sub._reexport_sample.A.a"}
    assert filter_spec_module_prefix(
        manager.context.whitelist, "tests.test_pkg.sub._reexport_sample"
    ) == {
        "tests.test_pkg.sub._reexport_sample._fc",
        "tests.test_pkg.sub._reexport_sample.A._e",
        "tests.test_pkg.sub._reexport_sample.A",
        "tests.test_pkg.sub._reexport_sample._fe",
        "tests.test_pkg.sub._reexport_sample.fa",
        "tests.test_pkg.sub._reexport_sample.A._c",
    }
    assert flat_external(filter_type(test_module.members, External)) == {
        "fa": "tests.test_pkg.sub._reexport_sample.fa",
        "_fc": "tests.test_pkg.sub._reexport_sample._fc",
        "A": "tests.test_pkg.sub._reexport_sample.A",
    }
    assert flat_libraryattr(filter_type(test_module.members, LibraryAttr)) == {
        "Path": ("Path", "pathlib.Path docstring...")
    }


def test_member_filter():
    manager = ModuleManager("tests.test_pkg.sub")
    test_module = manager.modules["tests.test_pkg.sub.member_filter"]
    assert not test_module.is_package
