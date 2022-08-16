# type: ignore
from typing import Dict, Union

import pytest

from nb_autodoc.inspector import Module, Variable, _modules


@pytest.fixture
def module_only_globalns():
    module = lambda: ...
    module.name = "dummy_module"
    module.globalns = {"Module": Module}
    module._evaluate = lambda s: Module._evaluate(module, s)

    return module


def test_Module():
    module = Module("tests.test_pkg")
    context = module.context
    ...


def test_Variable_annotation(module_only_globalns):
    var1 = Variable("<unknown>", module_only_globalns)
    assert var1.annotation == "untyped"
    var1._annot = "X"  # test cached_property
    assert var1.annotation == "untyped"
    getannot = lambda x: Variable("<unknown>", module_only_globalns, x).annotation
    assert getannot(...) == "untyped"
    assert getannot(None) == "None"
    assert getannot("(int,str)->str") == "(int,str)->str"
    assert getannot("Module") == "nb_autodoc.inspector.Module"
    assert getannot("X") == "X"
    assert getannot(Union[int, str]) == "int | str"
    assert getannot(Union[int, "Module"]) == "int | nb_autodoc.inspector.Module"
    assert getannot(Union[int, "Unknown"]) == "int | Unknown"
    assert (
        getannot(Union[Dict[str, "Module"], "Unknown"])
        == "dict[str, nb_autodoc.inspector.Module] | Unknown"
    )
