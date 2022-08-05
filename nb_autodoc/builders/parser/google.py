"""Google Style Docstring Parser.
"""
import re
from functools import wraps
from typing import TYPE_CHECKING, Callable, List, Optional, TypeVar, cast
from typing_extensions import Concatenate, ParamSpec

from nb_autodoc.builders.nodes import (
    Args,
    Docstring,
    InlineValue,
    Role,
    docstring,
    section,
)
from nb_autodoc.utils import dedent

if TYPE_CHECKING:
    from nb_autodoc.config import Config


TP = TypeVar("TP", bound="Parser")
P = ParamSpec("P")
RT = TypeVar("RT")
RTS = TypeVar("RTS", bound="section")


def record_pos(
    func: Callable[Concatenate[TP, P], RT]
) -> Callable[Concatenate[TP, P], RT]:
    """Parser Position Recorder."""

    @wraps(func)
    def recorder(self: TP, *args: P.args, **kwargs: P.kwargs) -> RT:
        lineno = self.lineno
        col = self.col
        obj = func(self, *args, **kwargs)  # after called, position moves to its ending
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
    _role_re = re.compile(r"{(\w+)}`(.+?)`", re.A)
    _firstline_re = re.compile(r"([a-zA-Z_][\w\. \[\],]*)(?<! ):(.+)", re.A)
    _section_marker_re = re.compile(r"(\w+) *(?:\(([0-9\.\+\-]+)\))? *:")

    # Annotation pattern is not precious, and it is difficult to support precious match.
    # CJK identifier name is impossible to support!

    _sections = {
        "Arguments": "args",
        "Args": "args",
        "Parameters": "args",
        "Params": "args",
        "参数": "args",
        "Attributes": "attributes",
        "属性": "attributes",
        "Example": "examples",
        "Examples": "examples",
        "示例": "examples",
        "用法": "examples",
        "FrontMatter": "frontmatter",
        "Meta": "frontmatter",
        "Raises": "raises",
        "Exceptions": "raises",
        "异常": "raises",
        "Return": "returns",
        "Returns": "returns",
        "返回": "returns",
        "Require": "require",
        "要求": "require",
        "Yield": "yields",
        "Yields": "yields",
        "生成器返回": "yields",
    }
    _inline_sections = {
        "Version": "version",
        "版本": "version",
        "TypeVersion": "typeversion",
        "类型版本": "typeversion",
    }

    def __init__(self, docstring: str, config: "Config") -> None:
        self.lines = docstring.splitlines()
        self.lineno = 0
        self.col = 0
        self.indent = config["docstring_section_indent"]

    @property
    def line(self) -> str:
        return self.lines[self.lineno][self.col :]

    def _spec_next_section(self) -> Optional[int]:
        lineno = None
        for i in range(self.lineno, len(self.lines)):
            if self._section_marker_re.match(self.lines[i]):
                lineno = i
                break
        return lineno

    def _spec_next_argcolon(self) -> int:
        ...

    def _consume_spaces(self) -> None:
        spaces = len(self.line) - len(self.line.lstrip())
        self.col += spaces

    def _consume_linebreaks(self) -> None:
        if self.line:
            return
        self.col = 0
        while not self.line and self.lineno + 1 < len(self.lines):
            self.lineno += 1

    def _consume_indent(self) -> None:
        if self.indent is None:
            return
        spaces = len(self.line) - len(self.line.lstrip())
        if spaces != self.indent:
            raise

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

    @record_pos
    def _section_manager(self, match: re.Match[str]) -> section:
        name, version = match.groups()
        if name in self._inline_sections:
            value = self.line[match.end() :].strip()
            self.lineno += 1
            self._consume_linebreaks()
            return InlineValue(name=name, value=value)
        self.lineno += 1
        try:
            consumer = getattr(self, "_consume_" + self._sections[name])
        except AttributeError:
            raise ParserError(f"{name} is not a valid section marker.")
        obj = consumer()
        obj.name = name
        if "version" in obj._fields:
            obj.version = version
        return obj

    @record_pos
    def _consume_args(self) -> Args:
        ...

    def parse(self) -> Docstring:
        roles = []
        annotation = None
        descr = ""
        long_descr = ""
        match = None
        partition_lineno = None
        for i in range(len(self.lines)):
            match = self._section_marker_re.match(self.lines[i])
            if match:
                partition_lineno = i
                break
        descr_chunk = self.lines[:partition_lineno]
        if descr_chunk:
            roles = self._consume_roles()
            match = self._firstline_re.match(self.line)
            if match:
                annotation, descr = match.groups()
            else:
                descr = self.line
            descr = descr.strip()
            if len(descr_chunk) > 1:
                long_descr = "\n".join(descr_chunk[1:]).strip()
        self.col = 0
        self.lineno = partition_lineno if partition_lineno is not None else 0
        sections = []
        while self.lineno + 1 <= len(self.lines):
            match = self._section_marker_re.match(self.line)
            if match:
                section = self._section_manager(match)
                sections.append(section)
            else:  # skip one line
                self.lineno += 1
                self.col = 0
            self._consume_spaces()
            self._consume_linebreaks()
        return Docstring(
            roles=roles,
            annotation=annotation,
            descr=descr,
            long_descr=long_descr,
            sections=sections,
        )


class ParserError(Exception):
    ...


a = Parser(
    """{v1}`1.1.0+` {v2}`1.2.0+` Union[int, str]: description.

long long long description.

Args (1.1.0+):
    ...

Returns:
    ...""",
    {"strict_mode": True, "docstring_section_indent": 4},
).parse()
...
