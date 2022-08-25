from typing import Dict, Tuple, Type, TypeVar

import pytest

from nb_autodoc.inspector import External, LibraryAttr, ModuleManager
from nb_autodoc.typing import T_ModuleMember

T = TypeVar("T")


@pytest.fixture(scope="module")
def main_modulemanager():
    return ModuleManager("tests.test_pkg", skip_modules={"tests.test_pkg.sub._foo"})


def flat_external(dct: Dict[str, External]) -> Dict[str, str]:
    return {k: v.refname for k, v in dct.items()}


def flat_libraryattr(dct: Dict[str, LibraryAttr]) -> Dict[str, Tuple[str, str]]:
    return {k: (v.docname, v.docstring) for k, v in dct.items()}


def filter_type(dct: Dict[str, T_ModuleMember], typ: Type[T]) -> Dict[str, T]:
    return {k: v for k, v in dct.items() if isinstance(v, typ)}


def test_resolve_autodoc():
    modulemanager = ModuleManager(
        "tests.test_pkg.sub", skip_modules={"tests.test_pkg.sub._foo"}
    )
    _sub_module = modulemanager.modules["tests.test_pkg.sub"]
    assert _sub_module.is_package
    assert modulemanager.context.blacklist == {"tests.test_pkg.sub._foo.A.a"}
    assert modulemanager.context.whitelist == {
        "tests.test_pkg.sub._foo._fc",
        "tests.test_pkg.sub._foo.A._e",
        "tests.test_pkg.sub._foo.A",
        "tests.test_pkg.sub._foo._fe",
        "tests.test_pkg.sub._foo.fa",
        "tests.test_pkg.sub._foo.A._c",
    }
    assert flat_external(filter_type(_sub_module.members, External)) == {
        "fa": "tests.test_pkg.sub._foo.fa",
        "_fc": "tests.test_pkg.sub._foo._fc",
        "A": "tests.test_pkg.sub._foo.A",
    }
    assert flat_libraryattr(filter_type(_sub_module.members, LibraryAttr)) == {
        "Path": ("Path", "pathlib.Path docstring...")
    }
