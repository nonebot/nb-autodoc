import click

from nb_autodoc import Module
from nb_autodoc.builders.markdown import MarkdownBuilder
from nb_autodoc.builders import helpers


@click.command()
@click.option("--vuepress", default=False, is_flag=True)
@click.option("-o", "--output-dir", default="build")
@click.argument("module_name")
def cli_main(module_name, output_dir, vuepress):
    module = Module(module_name)
    builder = MarkdownBuilder(
        module,
        output_dir=output_dir,
        slugify=helpers.vuepress_slugify if vuepress else None,
    )
    builder.write()


if __name__ == "__main__":
    cli_main()
