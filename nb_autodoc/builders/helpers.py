import re
from typing import Callable, Match

from nb_autodoc import Doc, Context


def linkify(
    annotation: str, *, add_link: Callable[[Doc], str], context: Context
) -> str:
    """
    Add url link for annotation.

    Args:
        annotation: Type's repr get from formatannotation
        add_link: add url link for refname found.
    """

    def _add_link(match: Match) -> str:
        refname = match.group()
        dobj = context.get(refname)
        if not dobj:
            return refname
        return add_link(dobj)

    annotation = re.sub(r"[A-Za-z0-9_\.]+", _add_link, annotation)

    return annotation


def vuepress_slugify(s: str) -> str:
    """Slugify implementation duplicated from vuepress."""
    s = re.sub(r"[\u0300-\u036F\u0000-\u001f]", "", s)
    s = re.sub(r"[\s~`!@#$%^&*()\-_+=[\]{}|\\;:\"'“”‘’–—<>,.?/]+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    s = re.sub(r"^-+|-+$", "", s)
    s = re.sub(r"^(\d)", r"_\g<1>", s)
    return s.lower()
