from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable, ClassVar


class DocumentMeta(type):
    def __init__(
        cls, name: str, bases: tuple[type, ...], namespace: dict[str, Any]
    ) -> None:
        # TODO: add slots support
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
        self: object = type.__call__(cls)
        if len(args) > len(cls._fields):
            raise TypeError(
                f"{cls.__name__} constructor takes at most "
                f"{len(cls._fields)} positional arguments"
            )
        obj_dict = self.__dict__ = dict.fromkeys(cls._fields)
        obj_dict.update(zip(cls._fields, args))
        obj_dict.update(kwargs)
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
    doc: Docstring | None


class Variable(root):
    name: _identifier
    kind: str
    annotation: str  # "untyped" if not exists
    doc: Docstring | None


class Function(root):
    name: _identifier
    kind: str
    p_signature: str  # type-removed parameter signature
    doc: Docstring | None


class Class(root):
    name: _identifier
    kind: str
    p_signature: str
    doc: Docstring | None
    body: list[root]


# Abstract Docstring for Builder


class docstring(Document):
    lineno: int
    col: int
    end_lineno: int
    end_col: int


class Docstring(docstring):
    roles: list[Role]
    annotation: str | None  # only variable should be contained
    descr: str
    long_descr: str
    sections: list[section]


class Role(docstring):
    name: _identifier
    text: str | None
    content: str


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
    args: list[ColonArg]  # identifier


class Examples(section):
    name: str
    value: str


# class KeywordArgs(section): ...


class FrontMatter(section):
    name: str
    value: str  # maybe dict


class Raises(section):
    name: str
    args: list[ColonArg]  # identifier or attribute


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
