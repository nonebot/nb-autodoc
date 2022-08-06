"""Google Style Docstring Parser.
"""
import re
import warnings
from functools import lru_cache, wraps
from typing import TYPE_CHECKING, Callable, List, Optional, TypeVar, cast
from typing_extensions import Concatenate, ParamSpec

from nb_autodoc.nodes import (
    Args,
    ColonArg,
    Docstring,
    InlineValue,
    Returns,
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
    _role_re = re.compile(r"{(\w+)}`(.+?)`", re.A)
    _firstline_re = re.compile(r"([a-zA-Z_][\w\. \[\],]*)(?<! ):(.+)", re.A)
    _section_marker_re = re.compile(r"(\w+) *(?:\(([0-9\.\+\-]+)\))? *:")
    _identifier_re = re.compile(r"[^\W0-9]\w*")
    _anno_re = re.compile(r"[a-zA-Z_][\w\. \[\],]*(?<! )", re.A)
    _pair_anno_re = re.compile(r"\(([a-zA-Z_][\w\. \[\],]*)\)", re.A)
    _vararg_re = re.compile(r" *\*[^\W0-9]")
    _kwarg_re = re.compile(r" *\*\*[^\W0-9]")

    # Annotation pattern is not precious, and it is difficult to support precious match.
    # CJK identifier name in annotation is impossible to support!
    # CJK identifier name is OK in a section ColonArg.

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
        self.lines.append("")  # ending of docstring
        self.lineno = 0
        self.col = 0
        self._indent = config["docstring_section_indent"]

    @property
    def line(self) -> str:
        return self.lines[self.lineno][self.col :]

    @property
    def indent(self) -> int:
        if self._indent is None:
            raise ParserError("indent is not specified.")
        return self._indent

    @lru_cache(1)
    def _find_first_marker(self) -> Optional[int]:
        partition_lineno = None
        for i in range(len(self.lines)):
            match = self._section_marker_re.match(self.lines[i])
            if match:
                partition_lineno = i
                break
        return partition_lineno

    def _consume_spaces(self) -> None:
        spaces = len(self.line) - len(self.line.lstrip())
        self.col += spaces

    def _consume_linebreaks(self) -> None:
        if self.line:
            return
        self.col = 0
        while not self.line and self.lineno + 1 < len(self.lines):
            self.lineno += 1

    def _consume_indent(self, num: int = 1) -> None:
        """Ensure the indent is correct."""
        spaces = len(self.line) - len(self.line.lstrip())
        if spaces != self.indent * num:
            raise ParserError("try to consume indent that is inconsistent.")
        self.col += self.indent * num

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

    def _consume_colonarg_descr(
        self, obj: Optional[ColonArg], least_indent: int, include_short: bool = True
    ) -> List[str]:
        if include_short:
            descr = self.line.strip()
            if obj is not None:
                obj.descr = descr
            self.col = 0
            self.lineno += 1
        descr_chunk = []
        breaked = False
        for i in range(self.lineno, len(self.lines)):
            line = self.lines[i]
            if line and len(line) - len(line.lstrip()) < least_indent:
                breaked = True
                break
            descr_chunk.append(line)
        if breaked:
            self.lineno += len(descr_chunk)
        else:
            self.lineno = len(self.lines) - 1  # move to ending
        long_descr = dedent("\n".join(descr_chunk)).strip()
        if obj is not None:
            obj.long_descr = long_descr
        return descr_chunk

    @record_pos
    def _consume_colonarg(self, partial_indent: bool = True) -> ColonArg:
        annotation = None
        if partial_indent:
            self._consume_indent()
        match = self._identifier_re.match(self.line)
        if not match:
            raise ParserError
        name = match.group()
        self.col += match.end()
        self._consume_spaces()
        match = self._pair_anno_re.match(self.line)
        if match:
            annotation = match.group(1)
            self.col += len(match.group())
        roles = self._consume_roles()
        if not self.line or self.line[0] != ":":
            raise ParserError("no colon found.")
        self.col += 1
        obj = ColonArg(name=name, annotation=annotation, roles=roles)
        self._consume_colonarg_descr(obj, self.indent + 1)
        return obj

    @record_pos
    def _section_manager(self, match: re.Match[str]) -> section:
        name, version = match.groups()
        if name in self._inline_sections:
            value = self.line[match.end() :].strip()
            self.lineno += 1
            self._consume_linebreaks()
            return InlineValue(name=name, value=value)
        self.lineno += 1
        self._consume_linebreaks()
        try:
            consumer = getattr(self, "_consume_" + self._sections[name])
        except KeyError:
            raise ParserError(f"{name} is not a valid section marker.")
        # Detect docstring indent in first non-inline section
        indent = len(self.line) - len(self.line.lstrip())
        if self._indent is None:
            self._indent = indent
        obj = consumer()
        obj.name = name
        if "version" in obj._fields:
            obj.version = version
        return obj

    def _consume_args(self) -> Args:
        args = []
        vararg = None
        kwarg = None
        while self.line and self.line.startswith(" "):
            self._consume_indent()
            if self.line.startswith("**"):
                self.col += 2
                kwarg = self._consume_colonarg(partial_indent=False)
            elif self.line.startswith("*"):
                self.col += 1
                vararg = self._consume_colonarg(partial_indent=False)
            else:
                args.append(self._consume_colonarg(partial_indent=False))
        return Args(args=args, vararg=vararg, kwarg=kwarg)

    def _consume_returns(self) -> Returns:
        value = ""  # type: str | ColonArg
        self._consume_indent()
        before, colon, after = self.line.partition(":")
        match = self._anno_re.match(before)
        if colon and match:
            value = ColonArg(name=match.group(), descr=after.strip())
            self.lineno += 1
            self.col = 0
        if isinstance(value, ColonArg):
            self._consume_colonarg_descr(value, self.indent, include_short=False)
        else:
            descr_chunk = self._consume_colonarg_descr(
                None, self.indent, include_short=False
            )
            value = "\n".join(descr_chunk).strip()
        return Returns(value=value)

    def parse(self) -> Docstring:
        roles = []
        annotation = None
        descr = ""
        long_descr = ""
        match = None
        partition_lineno = self._find_first_marker()
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
        while self.lineno <= len(self.lines) - 2:  # ending is empty string
            match = self._section_marker_re.match(self.line)
            if match:
                section = self._section_manager(match)
                sections.append(section)
            else:  # Skip one line
                # This branch should not execute
                # Possibly caused by mixing uncognized and detended things between two sections
                warnings.warn("the line has not been fully consumed.")
                self.lineno += 1
                self.col = 0
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

Version: 1.1.0+

Args (1.1.0+):

    a (Union[str, int]) {v}`1.1.0+`  : desc
    b: desc
        long long
        long long desc.

    c: desc
    *d: desc
    **e (Union[str, int]) {v}`1.1.0+` : desc

        long and long
        long long desc.

Returns:
    ...

""",
    {"strict_mode": True, "docstring_section_indent": None},
).parse()
...
