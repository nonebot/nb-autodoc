from nb_autodoc import Module, Context
from nb_autodoc.builders.markdown import MarkdownBuilder


context = Context()


module = Module("test_pkg", context=context)

builder = MarkdownBuilder(module, output_dir="build")

builder.write()


exit(0)
