from typing import ClassVar, NamedTuple


class A(NamedTuple):
    a: int

    def f(self) -> bool:
        ...


class B:
    a: int
    b: int = 1
    c = 1
    d: ClassVar[int]

    def __init__(self) -> None:
        self.e: int

    def _call_impl(self, x: str) -> str:
        ...

    __call__ = _call_impl

    __getitem__ = lambda self, key: key
