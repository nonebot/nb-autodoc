import re
from typing import Tuple

_whitespace_re = re.compile(r"^([ \t]+)(?:\S)", re.MULTILINE)
_no_whitespace_re = re.compile(r"^\S", re.MULTILINE)


def dedent(s: str) -> Tuple[int, str]:
    """Enhanced version of `textwrap.dedent`.

    * Pretty better preformance (powered by pytest-benchmark).
    """
    # TODO: Remove re should get better performance
    if _no_whitespace_re.findall(s):
        return 0, s
    indents = [len(i) for i in _whitespace_re.findall(s)]
    margin = min(indents)
    # re.sub seems not working on re.M flag, which inline flag done
    s = re.sub("(?m)^" + " " * margin, "", s)
    return margin, s


def cleandoc(s: str, strict: bool = False) -> str:
    """Enhanced version of `inspect.cleandoc`.

    * Fix `inspect.cleandoc` do not remove blank only lines (strict mode).
    * Slightly better performance (powered by pytest-benchmark).
    """
    lines = s.strip().expandtabs().splitlines()
    if strict:
        if any(line.isspace() for line in lines):
            raise ValueError
    margin = len(lines[-1]) - len(lines[-1].lstrip())
    for line in lines[1:]:
        if line:
            margin = min(margin, len(line) - len(line.lstrip()))
    for i in range(1, len(lines)):
        lines[i] = lines[i][margin:]
    return "\n".join(lines)
