import click

from nb_autodoc.log import logger

logger.setLevel("INFO")


@click.command()
@click.argument("module_name")
@click.option("-o", "--output-dir", default="build")
def main(module_name: str, output_dir: str) -> None:
    ...


if __name__ == "__main__":
    main()
