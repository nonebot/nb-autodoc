from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable, ClassVar


class DocumentMeta(type):
    def __init__(
        cls, name: str, bases: tuple[type, ...], namespace: dict[str, Any]
    ) -> None:
        """Validate class namespace before class creation."""
        return super().__init__(name, bases, namespace)

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        """Special dataclass implementation.

        This share the call for instance creation.
        """
        self = super().__call__()
        return self


class MappingMixin(Mapping):
    # not implemented yet
    def __init__(self) -> None:
        raise NotImplementedError


class Document(metaclass=DocumentMeta):
    _fields: ClassVar[tuple[str, ...]]

    __init__: Callable[..., None] = lambda self, *args, **kwargs: None


class Page(Document):
    body: list[root]


class root(Document):
    ...


_identifier = str


class Variable(root):
    name: _identifier
    kind: str
    annotation: str  # "untyped" if not exists
    doc: Docstring


class Function(root):
    name: _identifier
    kind: str
    p_signature: str  # type-removed parameter signature
    doc: Docstring


class Class(root):
    name: _identifier
    kind: str
    p_signature: str
    doc: Docstring
    body: list[root]


# parser store
class docstring(Document):
    lineno: int
    col: int
    end_lineno: int
    end_col: int


class Docstring(docstring):
    descr: str
    long_descr: str
    sections: list[section]


class Argument(docstring):
    name: str  # maybe not identifier, in `Returns` is anno
    annotation: str | None
    descr: str
    long_descr: str


class Text(docstring):
    s: str


class section(docstring):
    ...


class Args(section):
    args: list[Argument]
    vararg: Argument
    kwarg: Argument


class Returns(section):
    value: Text | Argument


class Attributes(section):
    args: list[Argument]


class Raises(section):
    args: list[Argument]


class Examples(section):
    value: Text


class Require(section):
    value: Text
