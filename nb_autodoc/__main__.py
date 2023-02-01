from typing import Tuple
from typing_extensions import Literal

import click

from nb_autodoc.builders.markdown import MarkdownBuilder
from nb_autodoc.config import Config
from nb_autodoc.log import logger
from nb_autodoc.manager import ModuleManager

logger.setLevel("INFO")


@click.command()
@click.argument("module", required=True)
@click.option(
    "-o",
    "--output-dir",
    default="build",
    type=click.Path(exists=False, file_okay=False, writable=True, executable=True),
    show_default=True,
)
@click.option("-s", "--skip", multiple=True, help="skip import modules")
@click.option("-u", "--undoc", multiple=True, help="undocument modules")
@click.option(
    "--markdown-linkmode",
    default="heading_id",
    type=click.Choice(["heading_id", "vuepress"]),
    show_default=True,
)
def main(
    module: str,
    output_dir: str,
    skip: Tuple[str, ...],
    undoc: Tuple[str, ...],
    markdown_linkmode: Literal["heading_id", "vuepress"],
) -> None:
    manager = ModuleManager(
        module,
        config=Config(
            output_dir=output_dir,
            skip_import_modules=set(skip),
            exclude_documentation_modules=set(undoc),
        ),
    )
    builder = MarkdownBuilder(manager, link_mode=markdown_linkmode)
    builder.write()


if __name__ == "__main__":
    main()
