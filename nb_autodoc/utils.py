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
    """Improved `inspect.cleandoc`."""
    s = s.strip().expandtabs()
    s = _space_only_re.sub("", s)
    chunk = s.split("\n", 1)
    if len(chunk) == 1:
        return chunk[0]
    firstline, body = chunk
    margin = detect_indent(body, ignore_blank_line=False)
    bodylines = body.splitlines()
    for i in range(len(bodylines)):
        bodylines[i] = bodylines[i][margin:]
    return firstline + "\n" + "\n".join(bodylines)
