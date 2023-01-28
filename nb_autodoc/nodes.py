from __future__ import annotations

from inspect import Signature
from typing import Any, Callable, ClassVar, Mapping, Type, TypeVar
from typing_extensions import Literal

TD = TypeVar("TD", bound="Document")


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


def eq_mixin(cls: Type[TD]) -> Type[TD]:
    def eq_impl(self: TD, other: object) -> bool:
        if not isinstance(other, cls):
            return False
        for field in self._fields:
            if getattr(self, field) != getattr(other, field):
                return False
        return True

    setattr(cls, "__eq__", eq_impl)
    return cls


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


class Function(root):
    name: _identifier
    kind: str
    signature: Signature
    doc: Docstring | None


class EnumType(root):
    name: str
    body: list[Variable]


class NamedTupleType(root):
    name: str
    signature: Signature
    doc: Docstring | None
    body: list[Variable | Function]


class Class(root):
    name: _identifier
    kind: str
    signature: Signature
    doc: Docstring | None
    body: list[root]


class Variable(root):
    name: _identifier
    # var, class-var, instance-var, property. specially class or lambda
    kind: str
    annotation: str  # "untyped" if not exists
    doc: Docstring | None


# Abstract Docstring for Builder


@eq_mixin
class docstring(Document):
    lineno: int
    col: int
    end_lineno: int
    end_col: int


class Docstring(docstring):
    roles: list[Role]
    annotation: str | None  # only variable should be contained
    # if long_descr exists, then descr exists too
    descr: str
    long_descr: str
    sections: list[section]


class Role(docstring):
    name: _identifier
    text: str | None
    content: str


class ColonArg(docstring):
    name: str | None  # None in `Returns`
    annotation: str | None
    roles: list[Role]
    descr: str
    long_descr: str


class section(docstring):
    ...


class InlineValue(section):
    name: str
    type: Literal["version", "typeversion"]
    value: str


class FrontMatter(section):
    name: str
    value: str  # maybe dict


class Text(section):
    # the text between two section
    value: str


class Args(section):
    name: str
    args: list[ColonArg]
    vararg: ColonArg | None
    kwonlyargs: list[ColonArg]
    kwarg: ColonArg | None


class Attributes(section):
    name: str
    args: list[ColonArg]


class Examples(section):
    name: str
    value: str


# class KeywordArgs(section): ...


class Raises(section):
    name: str
    # arg only have annotation (must be attr) and description
    # like `exception.ApiError: descr`
    args: list[ColonArg]


class Returns(section):
    name: str
    version: str | None
    # if value is arg, it only have annotation and description
    value: str | ColonArg


class Yields(section):
    name: str
    version: str | None
    value: str | ColonArg


class Require(section):
    name: str
    version: str | None
    value: str
