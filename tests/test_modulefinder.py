from typing import Any
import pytest

from nb_autodoc.config import default_config
from nb_autodoc.modulefinder import ModuleFinder, _Finder
from tests.utils import uncache_import

_PATH = "tests/modulefinderdata"


class TestModuleFinder:
    @pytest.fixture(autouse=True)
    def _setup(self):
        ...

    def test_is_exclude_module(self):
        config: Any = {"skip_import_modules": {"pkg.*"}}
        basefinder = _Finder(config)
        assert not basefinder.is_exclude_module("pkg")
        assert basefinder.is_exclude_module("pkg.echo")

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

    def test_find_all_modules_wrapped(self):
        with uncache_import(_PATH, "simplepkg"):
            finder = ModuleFinder(default_config)
            modules, stubs = finder.find_all_modules_wrapped("simplepkg")
        assert list(modules.keys()) == [
            "simplepkg",
            "simplepkg.foo",
            "simplepkg.simplenamespace",
            "simplepkg.simplenamespace.portion1",
            "simplepkg.simplenamespace.portion2",
            "simplepkg.sub",
            "simplepkg.sub.a",
        ]
        assert modules["simplepkg.sub"].is_package == True
