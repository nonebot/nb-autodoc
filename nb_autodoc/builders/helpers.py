import re
from typing import Callable, Match

from nb_autodoc import Doc, Context


def linkify(
    annotation: str, *, add_link: Callable[[Doc], str], context: Context
) -> str:
    """
    Function for re.sub to replace refname with link.

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
