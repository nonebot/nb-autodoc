"""
Documentation builder.
"""
import abc
from pathlib import Path
from typing import Dict, Set

from nb_autodoc import Doc, Module, Class, Function, Variable, LibraryAttr
from nb_autodoc.builders.parser.google import Docstring


class Builder(abc.ABC):
    def __init__(self, dmodule: Module, *, output_dir: str) -> None:
        self.dmodule = dmodule
        self.output_dir = output_dir

    def get_write_file(self, dobj: Doc) -> Path:
        return Path(self.output_dir, *dobj.refname.split("."))

    @abc.abstractmethod
    def write(self) -> None:
        raise NotImplementedError
