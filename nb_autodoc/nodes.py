from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable, ClassVar


class DocumentMeta(type):
    def __init__(
        cls, name: str, bases: tuple[type, ...], namespace: dict[str, Any]
    ) -> None:
        super().__init__(name, bases, namespace)
        annotations = getattr(cls, "__annotations__", {})
        # create _fields implicitly
        cls._fields: tuple[str, ...] = (
            tuple()
            if not cls.__name__[0].isupper() or cls.__base__ is object
            else tuple(annotations.keys())
        )

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        """Special dataclass implementation by hooking instance creation."""
        self: type = super().__call__()
        for k, v in kwargs.items():
            setattr(self, k, v)
        if len(args) > len(cls._fields):
            raise TypeError(
                f"{cls.__name__} constructor takes at most "
                f"{len(cls._fields)} positional arguments"
            )
        for i, v in enumerate(args):
            setattr(self, cls._fields[i], v)
        return self


class MappingMixin(Mapping[str, Any]):
    # not implemented yet
    def __init__(self) -> None:
        raise NotImplementedError


class Document(metaclass=DocumentMeta):
    _fields: ClassVar[tuple[str, ...]]

    # only type hint because parameters were never passed in
    __init__: Callable[..., None]


class Page(Document):
    body: list[root]


class root(Document):
    ...


_identifier = str


class Module(root):
    name: str
    doc: Docstring


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


class Role(docstring):
    name: _identifier
    text: str | None
    content: str


class Docstring(docstring):
    roles: list[Role]
    annotation: str | None  # only variable should be contained
    descr: str
    long_descr: str
    sections: list[section]


class ColonArg(docstring):
    name: str  # maybe not identifier, in `Returns` is anno
    annotation: str | None
    roles: list[Role]
    descr: str
    long_descr: str


class section(docstring):
    ...


class InlineValue(section):
    name: str
    value: str


class Args(section):
    name: str
    args: list[ColonArg]
    vararg: ColonArg | None
    kwarg: ColonArg | None


class Attributes(section):
    name: str
    args: list[ColonArg]


class Examples(section):
    name: str
    value: str


# class KeywordArgs(section): ...


class FrontMatter(section):
    name: str
    value: str  # maybe dict


class Raises(section):
    name: str
    args: list[ColonArg]


class Returns(section):
    name: str
    version: str | None
    value: str | ColonArg


class Require(section):
    name: str
    version: str | None
    value: str


class Yields(section):
    name: str
    value: str | ColonArg
