"""Skipped module that has some reexport members."""


def fa(x: int) -> None:
    """reexport in test_pkg.sub"""


def fb(x: int) -> None:
    ...


def _fc(x: int) -> None:
    """reexport (whitelist) in test_pkg.sub"""


def _fd(x: int) -> None:
    """not documented for startswith underscore or dunder"""


def _fe(x: int) -> None:
    """force-export in current module but skip documentation..."""


class A:
    """reexport in test_pkg.sub"""

    def a(self) -> None:
        """not documented"""

    def b(self) -> None:
        ...

    def _c(self) -> None:
        """force-export"""

    def _d(self) -> None:
        ...

    def _e(self) -> None:
        """also can be controlled by current module"""


__autodoc__ = {"_fe": True, "A._e": True}
