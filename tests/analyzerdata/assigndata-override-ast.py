# type: ignore
# fmt: off


a = 1
"""a first docstring"""
a = 2
"""a overridden docstring"""  # ignored

b: int | None = 1
b: int  # update annotation and docstring
"""b first docstring"""
