# type: ignore
from typing import TYPE_CHECKING

a = 1


if TYPE_CHECKING:
    from nb_autodoc.manager import ModuleManager
    from loguru import Logger

    b = a

    def func() -> X | Y:
        ...
