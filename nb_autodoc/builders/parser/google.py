"""Google Style Docstring Parser.
"""
import re
from functools import wraps
from typing import Callable, List, Optional, TypeVar, cast
from typing_extensions import Concatenate, ParamSpec

from nb_autodoc.builders.nodes import Args, Docstring, Role, docstring

TP = TypeVar("TP", bound="Parser")
P = ParamSpec("P")
RT = TypeVar("RT")


def record_pos(
    func: Callable[Concatenate[TP, P], RT]
) -> Callable[Concatenate[TP, P], RT]:
    """Position Recorder.

    Record the position if func returns `PosWritable` object.
    """

    @wraps(func)
    def recorder(self: TP, *args: P.args, **kwargs: P.kwargs) -> RT:
        lineno = self.lineno
        col = self.col
        obj = func(self, *args, **kwargs)
        _obj = cast("Optional[docstring]", obj)
        # Ref for type hint, bound T not work for mypy
        # Also, generic operation is invalid in python
        end_lineno = self.lineno
        end_col = self.col
        if _obj is not None:
            _obj.lineno = lineno
            _obj.col = col
            _obj.end_lineno = end_lineno
            _obj.end_col = end_col
        return obj

    return recorder


class Parser:
    # re not support ambitious lookbehind width
    _arg_vararg_re = re.compile(r"(?:\*)([a-zA-Z_]\w*)")
    _arg_kwarg_re = re.compile(r"(?:\*\*)")
    _role_re = re.compile(r"{(\w+)}`(.+?)`")
    _anno_char = r"\w\. \[\],"  # \t not allow in annotation

    def __init__(self, docstring: str) -> None:
        self.lines = docstring.splitlines()
        self.lineno = 0
        self.col = 0

    @property
    def line(self) -> str:
        return self.lines[self.lineno][self.col :]

    def _consume_spaces(self) -> None:
        match = re.match(r"^ *", self.line)
        if match:
            self.col += match.end()

    def _consume_linebreak(self) -> None:
        if self.line:
            return
        self.col = 0
        while not self.line:
            self.lineno += 1

    @record_pos
    def _consume_role(self) -> Optional[Role]:
        match = self._role_re.match(self.line)
        if match:
            self.col += match.end()
            return Role(name=match.group(1), content=match.group(2))
        return None

    def _consume_roles(self) -> List[Role]:
        roles: List[Role] = []
        while True:
            self._consume_spaces()
            role = self._consume_role()
            if role is None:
                break
            roles.append(role)
        return roles

    def parse(self) -> Docstring:
        roles = self._consume_roles()
        self._consume_spaces()  # Unneeded check
        return Docstring(roles=roles)


a = Parser(
    """  {v1}`1.1.0+` {v2}`1.2.0+`

description.
"""
)
a.parse()
...
