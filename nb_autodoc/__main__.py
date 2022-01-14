import click

from nb_autodoc import Module
from nb_autodoc.builders.markdown import MarkdownBuilder


@click.command()
@click.option("-o", "--output-dir", default="build")
@click.argument("module_name")
def cli_main(module_name, output_dir):
    module = Module(module_name)
    builder = MarkdownBuilder(module, output_dir=output_dir)
    builder.write()


if __name__ == "__main__":
    cli_main()
