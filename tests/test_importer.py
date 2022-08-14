from nb_autodoc.importer import Module, _modules


def test_Module():
    module = Module("tests.test_pkg")
    context = module.context
    ...
