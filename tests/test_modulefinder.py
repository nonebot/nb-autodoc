import pytest

from nb_autodoc.config import default_config
from nb_autodoc.modulefinder import ModuleFinder
from tests.utils import uncache_import

_PATH = "tests/modulefinderdata"


class TestModuleFinder:
    @pytest.fixture(autouse=True)
    def _setup(self):
        ...

    def test_scan_modules(self):
        with uncache_import(_PATH, "simplepkg") as m:
            finder = ModuleFinder(default_config)
            modules, stubs = finder.scan_modules("simplepkg", m.__path__, ({}, {}))
        assert modules.keys() == {
            "simplepkg.sub",
            "simplepkg.sub.a",
            "simplepkg.foo",
            "simplepkg.simplenamespace.portion1",
            "simplepkg.simplenamespace.portion2",
        }
        assert hasattr(modules["simplepkg.sub"], "__path__")
        assert stubs.keys() == {
            "simplepkg.sub",
            "simplepkg.sub.a",
            "simplepkg.sub.stubalone",
            "simplepkg.stubalone",
            "simplepkg.foo",
            "simplepkg.simplenamespace.portion1",
        }
        assert stubs["simplepkg.sub"].is_package == True
        assert stubs["simplepkg.sub"].origin.endswith("__init__.pyi")
        assert stubs["simplepkg.foo"].origin.endswith("foo.pyi")
