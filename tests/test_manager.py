import pytest

from nb_autodoc.manager import Function, ModuleManager

from .utils import uncache_import


@pytest.fixture(scope="module", name="simple_manager")
def _():
    with uncache_import("tests", "simple_pkg"):
        return ModuleManager("simple_pkg")


# def test__refine_autodoc_from_ast(simple_manager: ModuleManager):
#     module = simple_manager.modules["simple_pkg"]
#     reexport = simple_manager.modules["simple_pkg.reexport"]
#     refine = _refine_autodoc_from_ast
#     assert refine(module, "___") == None
#     assert refine(module, "Foo") == AutodocRefineResult(
#         "simple_pkg", "Foo", False, False
#     )
#     assert refine(module, "Api") == AutodocRefineResult(
#         "simple_pkg.api", "Api", True, False
#     )
#     assert refine(module, "Union") == AutodocRefineResult(
#         "simple_pkg", "Union", False, True
#     )
#     assert refine(reexport, "inter_A") == AutodocRefineResult(
#         "simple_pkg.reexport._sample", "A", True, False
#     )
#     assert refine(reexport, "reexport_inter_A") == AutodocRefineResult(
#         "simple_pkg.reexport._sample", "A", True, False
#     )


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
        assert len(manager.modules) == 1
        single = manager.modules["tests.managerdata.single"]
        assert single.members.keys() == {"foo", "func"}

        with uncache_import("tests/managerdata", "single") as m:
            manager = ModuleManager(m)
            assert manager.name == "single"
            assert len(manager.modules) == 1
            single = manager.modules["single"]
            assert single.members.keys() == {"foo", "func"}

    def test_get_definition_dotted(self):
        manager = ModuleManager("tests.managerdata.get_canonical_member")
        moda = manager.modules["tests.managerdata.get_canonical_member.a"]
        modb = manager.modules["tests.managerdata.get_canonical_member.b"]
        moda_A_a = moda.members["A"].members["a"]
        moda_b = moda.members["b"]
        moda_B_b = moda.members["B"].members["b"]
        modb_a = modb.members["a"]
        modb_C = modb.members["C"]
        modb_C_c = modb_C.members["c"]
        assert (
            manager.get_definition("tests.managerdata.get_canonical_member.a", "C")
            is modb_C
        )
        assert (
            manager.get_definition("tests.managerdata.get_canonical_member.a", "b")
            is moda_b
        )
        assert (
            manager.get_definition_dotted(
                "tests.managerdata.get_canonical_member.a.A.a"
            )
            is moda_A_a
        )
        assert (
            manager.get_definition_dotted(
                "tests.managerdata.get_canonical_member.a.B.b"
            )
            is moda_B_b
        )
        assert (
            manager.get_definition_dotted("tests.managerdata.get_canonical_member.a.C")
            is modb_C
        )
        assert (
            manager.get_definition_dotted(
                "tests.managerdata.get_canonical_member.a.C.c"
            )
            is modb_C_c
        )
        assert (
            manager.get_definition_dotted(
                "tests.managerdata.get_canonical_member.a.B.c"
            )
            is modb_C_c
        )
        Foo_a = manager.modules["tests.managerdata.get_canonical_member.Foo"].members[
            "a"
        ]
        assert (
            manager.get_definition_dotted(
                "tests.managerdata.get_canonical_member.Foo.a"
            )
            is Foo_a
        )


class TestModule:
    def test_get_canonical_member(self):
        from .managerdata import get_canonical_member

        manager = ModuleManager(get_canonical_member)
        module = manager.modules["tests.managerdata.get_canonical_member.a"]
        assert (
            module.get_canonical_member("a").fullname
            == "tests.managerdata.get_canonical_member.b:a"
        )
        assert (
            module.get_canonical_member("b").fullname
            == "tests.managerdata.get_canonical_member.a:b"
        )
        assert (
            module.get_canonical_member("A.a").fullname
            == "tests.managerdata.get_canonical_member.a:A.a"
        )
        assert (
            module.get_canonical_member("B.a").fullname
            == "tests.managerdata.get_canonical_member.a:A.a"
        )
        assert (
            module.get_canonical_member("B.b").fullname
            == "tests.managerdata.get_canonical_member.a:B.b"
        )
        assert (
            module.get_canonical_member("B.c").fullname
            == "tests.managerdata.get_canonical_member.b:C.c"
        )


class TestClass:
    def test_instvar_combination(self):
        from .managerdata import class_instvar_combination

        manager = ModuleManager(class_instvar_combination)
        name, module = manager.modules.popitem()
        assert module.members["A"].members["a"].astobj.annotation.id == "str"
        assert module.members["A"].members["a"].astobj.docstring == "a docstring"
        assert module.members["A"].members["b"].astobj.docstring == "b docstring"

    def test_mro(self):
        from .managerdata import class_bases

        manager = ModuleManager(class_bases)
        module = manager.modules["tests.managerdata.class_bases"]
        module_base = manager.modules["tests.managerdata.class_bases.base"]
        assert module.members["Mixin"].mro == ()
        assert module.members["A"].mro == (
            module.members["Mixin"],
            module_base.members["Base"],
        )

    def test_prepare(self):
        from .managerdata import class_prepare

        manager = ModuleManager(class_prepare)
        module = manager.modules["tests.managerdata.class_prepare.instvar"]
        # NamedTuple fields is all instance var
        assert module.members["A"].members["a"].is_instvar is True
        assert module.members["A"].members["f"].__class__ is Function
        # normal class tests
        assert module.members["B"].members["a"].is_instvar is True
        assert module.members["B"].members["b"].is_instvar is False
        assert module.members["B"].members["c"].is_instvar is False
        assert module.members["B"].members["d"].is_instvar is False
        assert module.members["B"].members["e"].is_instvar is True
        assert module.members["B"].members["__call__"].__class__ is Function
        assert module.members["B"].members["__getitem__"].is_instvar is False
        # the instance var order is uncompromised but we check here
        assert list(module.members["B"].members.keys()) == [
            "a",
            "d",
            "e",
            "b",
            "c",
            "__init__",
            "_call_impl",
            "__call__",
            "__getitem__",
        ]


class TestVariable:
    def test_is_typealias(self):
        from .managerdata import variable_is_typealias

        manager = ModuleManager(variable_is_typealias)
        name, module = manager.modules.popitem()
        assert module.members["a"].is_typealias
        assert module.members["b"].is_typealias
        assert module.members["c"].is_typealias
        assert not module.members["d"].is_typealias
        assert not module.members["e"].is_typealias
