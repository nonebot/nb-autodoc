import ast
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    import re
    from email import *

    # isort: off
    from pathlib import Path as MyPath, PurePath as MyPurePath

    # isort: on

    from . import example_google_docstring as egd
    from .example_google_docstring import ExampleClass as ec


class A:
    ...
