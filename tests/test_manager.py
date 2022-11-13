import pytest

from nb_autodoc.manager import (
    AutodocRefineResult,
    LibraryAttr,
    ModuleManager,
    _refine_autodoc_from_ast,
)

from .utils import uncache_import


@pytest.fixture(scope="module", name="simple_manager")
def _():
    with uncache_import("tests", "simple_pkg"):
        return ModuleManager("simple_pkg")


def test__refine_autodoc_from_ast(simple_manager: ModuleManager):
    module = simple_manager.modules["simple_pkg"]
    reexport = simple_manager.modules["simple_pkg.reexport"]
    refine = _refine_autodoc_from_ast
    assert refine(module, "___") == None
    assert refine(module, "Foo") == AutodocRefineResult(
        "simple_pkg", "Foo", False, False
    )
    assert refine(module, "Api") == AutodocRefineResult(
        "simple_pkg.api", "Api", True, False
    )
    assert refine(module, "Union") == AutodocRefineResult(
        "simple_pkg", "Union", False, True
    )
    assert refine(reexport, "inter_A") == AutodocRefineResult(
        "simple_pkg.reexport._sample", "A", True, False
    )
    assert refine(reexport, "reexport_inter_A") == AutodocRefineResult(
        "simple_pkg.reexport._sample", "A", True, False
    )


class TestModuleManager:
    # def test_refine_autodoc(self, simple_manager: ModuleManager):
    #     assert simple_manager.whitelist == {
    #         "simple_pkg.Foo.__call__",
    #         "simple_pkg.reexport.Path",
    #         "simple_pkg.reexport._sample.fa",
    #         "simple_pkg.reexport._sample.A",
    #         "simple_pkg.reexport._sample._fc",
    #         "simple_pkg.reexport._sample.A._fc",
    #         "simple_pkg.reexport._sample.A._fe",
    #         "simple_pkg.reexport._sample._fe",
    #     }
    #     assert simple_manager.blacklist == {
    #         "simple_pkg.Foo.privatefunc",
    #         "simple_pkg.reexport._sample.A.fa",
    #     }
    #     has_reexport_check = ["simple_pkg.reexport"]
    #     assert simple_manager.modules["simple_pkg.reexport"].exist_external == {
    #         "fa": Reference("simple_pkg.reexport._sample", "fa"),
    #         "_fc": Reference("simple_pkg.reexport._sample", "_fc"),
    #         "A": Reference("simple_pkg.reexport._sample", "A"),
    #         "inter_A": Reference("simple_pkg.reexport._sample", "A"),
    #         "reexport_inter_A": Reference("simple_pkg.reexport._sample", "A"),
    #         "Path": LibraryAttr(
    #             "simple_pkg.reexport", "Path", "stdlib pathlib.Path docstring..."
    #         ),
    #     }
    #     # generic check empty reference / libraryattr
    #     for name in filter(
    #         lambda x: x not in has_reexport_check, simple_manager.modules
    #     ):
    #         module = simple_manager.modules[name]
    #         assert module.exist_external == {}

    def test_single_file_module(self):
        manager = ModuleManager("tests.managerdata.single")
        assert manager.name == "tests.managerdata.single"
        single = manager.modules["tests.managerdata.single"]
        assert single.members.keys() == {"foo", "func"}
        with uncache_import("tests/managerdata", "single") as m:
            manager = ModuleManager(m)
            assert manager.name == "single"
            single = manager.modules["single"]
            assert single.members.keys() == {"foo", "func"}
