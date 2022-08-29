from types import MappingProxyType
from typing import Optional, Set, TypedDict


class Config(TypedDict):
    strict: bool
    """Strict mode. Apply docstring validation. Defaults to True."""
    static: bool
    """Enable fully static code analysis. Defaults to False."""
    skip_modules: Set[str]
    docstring_section_indent: Optional[int]


default_config = MappingProxyType(
    Config(strict=True, static=False, skip_modules=set(), docstring_section_indent=None)
)
