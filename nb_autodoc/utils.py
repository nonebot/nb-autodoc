import logging

logger = logging.getLogger("nb_autodoc")
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
logger.addHandler(console_handler)


def dedent(s: str) -> str:
    """Enhanced version of `textwrap.dedent`.

    * Pretty better preformance (powered by pytest-benchmark).
    """
    lines = s.split("\n")  # splitlines will ignore the last newline
    margin = float("inf")
    for line in lines:
        if line:
            margin = min(margin, len(line) - len(line.lstrip()))
    # margin is only inf in case string empty
    if isinstance(margin, float):
        return s
    for i in range(len(lines)):
        lines[i] = lines[i][margin:]
    return "\n".join(lines)


def cleandoc(s: str, strict: bool = False) -> str:
    """Enhanced version of `inspect.cleandoc`.

    * Fix `inspect.cleandoc` do not remove space only lines (strict mode).
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
