import re
from typing import List, Union

_space_only_re = re.compile(r"^[ \t]+$", re.MULTILINE)
_whitespace_re = re.compile(r"^([ \t]+)(?:\S)", re.MULTILINE)
_no_whitespace_re = re.compile(r"^\S", re.MULTILINE)


def detect_indent(s: Union[str, List[str]], ignore_blank_line: bool = True) -> int:
    """Detect the maximum common leading space of string."""
    if isinstance(s, list):
        s = "\n".join(s)
    if _no_whitespace_re.findall(s):
        return 0
    if ignore_blank_line:
        s = _space_only_re.sub("", s)
    indents = [len(i) for i in _whitespace_re.findall(s)]
    if indents:
        return min(indents)
    return 0


def cleandoc(s: str) -> str:
    """Enhanced version of `inspect.cleandoc`.

    * Fix `inspect.cleandoc` do not remove blank only lines.
    * Slightly better performance (powered by pytest-benchmark).
    """
    lines = s.strip().expandtabs().splitlines()
    margin = len(lines[-1]) - len(lines[-1].lstrip())
    for i in range(1, len(lines)):
        if lines[i]:
            margin = min(margin, len(lines[i]) - len(lines[i].lstrip()))
    for i in range(1, len(lines)):
        lines[i] = lines[i][margin:]
    return "\n".join(lines)
