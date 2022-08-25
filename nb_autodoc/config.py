from typing import Optional, Set, TypedDict


class Config(TypedDict):
    strict: bool
    skip_modules: Set[str]
    docstring_section_indent: Optional[int]
