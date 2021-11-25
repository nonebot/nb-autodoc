from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class DocstringParam:
    """
    Formed in `name (annotation) <badge>: desc`.
    """

    name: str
    annotation: Optional[str] = None
    version: Optional[str] = None  # third-level version
    description: Optional[str] = None


@dataclass
class DocstringOverload:
    args: List[DocstringParam]
    returns: List[DocstringParam]


@dataclass
class DocstringSection:
    """
    Attributes:
        content: empty when text not match regex, that directly render source
        overloads: key is the signature_repr, value is list of DocstringOverload.
    """

    identity: str
    content: List[DocstringParam]
    source: str
    overloads: Dict[str, DocstringOverload]
    version: Optional[str] = None  # second-level version

    def __str__(self) -> str:
        return self.source

    def __bool__(self) -> bool:
        if self.content or self.source:
            return True
        return False
