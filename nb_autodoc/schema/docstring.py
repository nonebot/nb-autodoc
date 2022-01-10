from typing import List, NamedTuple, Optional

from attrs import define, field


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
        content: empty when text not match regex, that directly render source
    """

    identity: str
    content: List[DocstringParam] = field(factory=list)
    source: str = ""
    version: Optional[str] = None  # second-level version

    def __str__(self) -> str:
        return self.source

    def __bool__(self) -> bool:
        if self.content or self.source:
            return True
        return False
