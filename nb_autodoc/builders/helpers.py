import re
from typing import TypeVar

T = TypeVar("T")


def vuepress_slugify(s: str) -> str:
    """Vuepress slugify implementation."""
    s = re.sub(r"[\u0300-\u036F\u0000-\u001f]", "", s)
    s = re.sub(r"[\s~`!@#$%^&*()\-_+=[\]{}|\\;:\"'“”‘’–—<>,.?/]+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    s = re.sub(r"^-+|-+$", "", s)
    s = re.sub(r"^(\d)", r"_\g<1>", s)
    return s.lower()
