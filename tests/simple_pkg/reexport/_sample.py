"""Skipped module that has some reexport members."""


def fa(x: int) -> None:
    """reexport in package"""


def fb(x: int) -> None:
    ...


def _fc(x: int) -> None:
    """reexport (whitelist) in package"""


def _fd(x: int) -> None:
    """not documented for startswith underscore or dunder"""


def _fe(x: int) -> None:
    """force-export in current module"""


class A:
    """reexport in test_pkg.sub"""

    def fa(self) -> None:
        """not documented"""

    def fb(self) -> None:
        """auto documented"""

    def _fc(self) -> None:
        """force-export"""

    def _fd(self) -> None:
        """auto blacklisted"""

    def _fe(self) -> None:
        """be controlled by autodoc var"""


__autodoc__ = {"_fe": True, "A._fe": True}
