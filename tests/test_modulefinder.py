from operator import attrgetter

import pytest

from nb_autodoc.config import default_config
from nb_autodoc.modulefinder import ModuleFinder
from tests.utils import uncache_import

_PATH = "tests/modulefinderdata"


class TestModuleFinder:
    @pytest.fixture(autouse=True)
    def _setup(self):
        ...

    def test_iter_modules(self):
        with uncache_import(_PATH, "simplepkg") as m:
            finder = ModuleFinder(default_config)
            orig_res = list(
                (i.__name__, i) for i in finder.iter_modules("simplepkg", m.__path__)
            )
            res = dict(orig_res)
            assert len(orig_res) == len(res)
            assert hasattr(res["simplepkg.sub"], "__path__")
            assert attrgetter("__spec__.origin")(res["simplepkg.foo"]).endswith(
                "foo.py"
            )
            assert "simplepkg.simplenamespace" not in res
            assert res["simplepkg.simplenamespace.portion1"]
            assert res["simplepkg.simplenamespace.portion2"]
