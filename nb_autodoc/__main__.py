from typing import Tuple

import click

from nb_autodoc.log import logger

logger.setLevel("INFO")


@click.command()
@click.argument("modules", nargs=-1, required=True)
@click.option(
    "-o",
    "--output-dir",
    default="build",
    type=click.Path(exists=False, file_okay=False, writable=True, executable=True),
)
def main(modules: Tuple[str, ...], output_dir: str) -> None:
    print(modules)


if __name__ == "__main__":
    main()
