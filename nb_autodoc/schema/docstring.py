import re
from typing import Dict, List, Optional

from attrs import define, field


def parse_roles(s: str) -> Dict[str, str]:
    return {
        match.group(1): match.group(2)
        for match in re.finditer(r"{([\w]+)}`([\w\.\[\], ]+)`", s)
    }


@define
class DocstringParam:
    """
    Formed in `name (annotation) rest: description`.
    rest should be Roles to determind version or such other things.
    """

    name: str
    annotation: Optional[str] = None
    # default is passing before convert
    rest: Dict[str, str] = field(converter=parse_roles, default="")
    description: Optional[str] = None


@define
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
