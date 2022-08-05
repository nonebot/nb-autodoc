from typing import Optional, TypedDict


class Config(TypedDict):
    strict_mode: bool
    docstring_section_indent: Optional[int]
