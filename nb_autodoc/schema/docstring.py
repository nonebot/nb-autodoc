from typing import List, NamedTuple, Optional
from enum import Enum

from attrs import define, field


class _SectionKind(Enum):
    SINGULAR = 0
    MULTIPLE = 1


class _SectionType(Enum):
    ARGS = 0
    RETURNS = 1
    ATTRIBUTES = 2
    RAISES = 3
    EXAMPLES = 4
    REQUIRE = 5
    VERSION = 6
    TYPE_VERSION = 7


@define(slots=True)
class DocstringParam:
    """
    Formed in `name (annotation) rest: description`.
    rest should be Roles to determind version or such other things.
    """

    name: str
    annotation: Optional[str] = None
    # default is passing before convert
    roles: List["Role"] = field(factory=list)
    description: Optional[str] = None
    long_description: Optional[str] = None

    class Role(NamedTuple):
        id: str
        content: str

    def __getattr__(self, name: str) -> Optional[str]:
        if name in ("version", "ref"):
            for role in self.roles:
                if name == role.id:
                    return role.content
            return None
        return self.__getattribute__(name)


@define(slots=True)
class DocstringSection:
    """
    Attributes:
        content: try parse source if kind is MULTIPLE
    """

    ARGS = _SectionType.ARGS
    RETURNS = _SectionType.RETURNS
    ATTRIBUTES = _SectionType.ATTRIBUTES
    RAISES = _SectionType.RAISES
    EXAMPLES = _SectionType.EXAMPLES
    REQUIRE = _SectionType.REQUIRE
    VERSION = _SectionType.VERSION
    TYPE_VERSION = _SectionType.TYPE_VERSION

    SINGULAR = _SectionKind.SINGULAR
    MULTIPLE = _SectionKind.MULTIPLE

    type: _SectionType
    kind: _SectionKind
    version: Optional[str] = None
    content: List[DocstringParam] = field(factory=list)
    source: str = ""

    def __str__(self) -> str:
        return self.source

    def __bool__(self) -> bool:
        if self.content or self.source:
            return True
        return False
