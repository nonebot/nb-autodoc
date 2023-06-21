"""Google Style Docstring Parser.
"""
import re
from functools import lru_cache, wraps
from typing import Callable, List, Match, Optional, Type, TypeVar, cast
from typing_extensions import Concatenate, ParamSpec

from nb_autodoc.log import logger
from nb_autodoc.nodes import (
    Args,
    Attributes,
    ColonArg,
    Docstring,
    Examples,
    FrontMatter,
    InlineValue,
    Raises,
    Require,
    Returns,
    Role,
    Text,
    Yields,
    docstring,
    section,
)
from nb_autodoc.utils import dedent

TP = TypeVar("TP", bound="GoogleStyleParser")
TS = TypeVar("TS", bound="section")
P = ParamSpec("P")
RT = TypeVar("RT")


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


class GoogleStyleParser:
    """Google style docstring parser."""

    _role_re = re.compile(r"{(\w+)}`(.+?)`", re.A)
    _firstline_re = re.compile(r"([a-zA-Z_][\w\. \[\],]*)(?<! ): *(\S+)", re.A)
    _section_marker_re = re.compile(r"(\w+) *(?:\(([0-9\.\+\-]+)\))? *:[^:]?")
    _identifier_re = re.compile(r"[^\W0-9]\w*")
    _anno_re = re.compile(r"[a-zA-Z_][\w\. \[\],]*(?<! )", re.A)
    _pair_anno_re = re.compile(r"\(([a-zA-Z_][\w\. \[\],]*)\)", re.A)
    _vararg_re = re.compile(r" *\*[^\W0-9]")
    _kwarg_re = re.compile(r" *\*\*[^\W0-9]")
    _attr_re = re.compile(r"[^\W0-9][\w\.]*", re.A)

    # Annotation pattern is not precious, and it is difficult to support precious match.
    # CJK identifier name in annotation is impossible to support!
    # CJK identifier name is OK in a section ColonArg.
    # CJK attribute name is not OK in section (Raises, etc.).

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
        "前言": "frontmatter",
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
        "Type-Version": "typeversion",
        "类型版本": "typeversion",
    }

    def __init__(self, doc: str, num_indent: Optional[int] = None) -> None:
        self.lines = doc.splitlines()
        self.lines.append("")  # ending of docstring
        self.lineno: int = 0
        self.col: int = 0
        # the number spaces of indent
        self._indent = num_indent

    @property
    def line(self) -> str:
        return self.lines[self.lineno][self.col :]

    @property
    def indent(self) -> int:
        if self._indent is None:
            raise ParserError("indent is not specified")
        return self._indent

    @lru_cache(1)
    def _find_first_marker(self) -> Optional[int]:
        partition_lineno = None
        for i in range(len(self.lines)):
            match = self._section_marker_re.match(self.lines[i])
            if match:
                if (
                    match.group(1)
                    not in self._sections.keys() | self._inline_sections.keys()
                ):
                    # maybe 'Anything:' in description
                    continue
                partition_lineno = i
                break
        return partition_lineno

    def _consume_spaces(self) -> None:
        spaces = len(self.line) - len(self.line.lstrip())
        self.col += spaces

    def _consume_linebreaks(self) -> None:
        if self.line or self.lineno == len(self.lines) - 1:
            return
        self.col = 0
        self.lineno += 1
        while self.lineno < len(self.lines) - 1 and not self.line:
            self.lineno += 1

    def _consume_indent(self) -> None:
        """Ensure the indent is correct."""
        spaces = len(self.line) - len(self.line.lstrip())
        if spaces != self.indent:
            raise ParserError(
                "try to consume indent that is inconsistent\n"
                + self._get_arounding_text(self.lineno)
            )
        self.col += self.indent

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

    def _consume_descr(
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
    def _consume_colonarg(self, remove_indent: bool = True) -> ColonArg:
        """Consume ColonArg until next ColonArg or detented line."""
        annotation = None
        if remove_indent:
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
            raise ParserError(
                "no colon found\n" + self._get_arounding_text(self.lineno)
            )
        self.col += 1
        obj = ColonArg(name=name, annotation=annotation, roles=roles)
        self._consume_descr(obj, self.indent + 1)
        return obj

    @record_pos
    def _section_dispatch(self, match: Match[str]) -> section:
        name, version = match.groups()
        marker_line = self.line
        self.lineno += 1
        self._consume_linebreaks()
        if name in self._inline_sections:
            type_ = self._inline_sections[name]
            value = marker_line[match.end() :].strip()
            return InlineValue(name=name, type=type_, value=value)
        try:
            consumer = getattr(self, "_consume_" + self._sections[name])
        except KeyError:
            raise ParserError(
                f"{name!r} is not a valid section marker, skipped\n"
                + self._get_arounding_text(self.lineno)
            ) from None
        # Detect docstring indent in first non-inline section
        indent = len(self.line) - len(self.line.lstrip())
        if self._indent is None:
            self._indent = indent
        obj = consumer()
        obj.name = name
        # some section like InlineValue or Example has no version
        if "version" in obj._fields:
            obj.version = version
        return obj

    def _consume_args(self) -> Args:
        args = []
        vararg = None
        kwonlyargs = []
        kwarg = None
        # linebreak has been consumed
        while self.line and self.line.startswith(" "):
            self._consume_indent()
            if self.line.startswith("**"):
                self.col += 2
                kwarg = self._consume_colonarg(remove_indent=False)
            elif self.line.startswith("*"):
                self.col += 1
                vararg = self._consume_colonarg(remove_indent=False)
            else:
                arg = self._consume_colonarg(remove_indent=False)
                if vararg:
                    kwonlyargs.append(arg)
                elif not kwarg:
                    args.append(arg)
                else:
                    raise ParserError(
                        "arg cannot follow **kwargs\n"
                        + self._get_arounding_text(self.lineno)
                    )
        return Args(args=args, vararg=vararg, kwonlyargs=kwonlyargs, kwarg=kwarg)

    def _consume_attributes(self) -> Attributes:
        args = []
        while self.line and self.line.startswith(" "):
            args.append(self._consume_colonarg())
        return Attributes(args=args)

    def _consume_examples(self) -> Examples:
        descr_chunk = self._consume_descr(None, self.indent, include_short=False)
        value = dedent("\n".join(descr_chunk)).strip()
        return Examples(value=value)

    def _consume_frontmatter(self) -> FrontMatter:
        descr_chunk = self._consume_descr(None, self.indent, include_short=False)
        value = dedent("\n".join(descr_chunk)).strip()
        return FrontMatter(value=value)

    def _consume_raises(self) -> Raises:
        args = []
        while self.line and self.line.startswith(" "):
            self._consume_indent()
            match = self._attr_re.match(self.line)
            if not match:
                raise ParserError
            exc_cls = match.group()
            self.col += match.end()
            self._consume_spaces()
            roles = self._consume_roles()
            if not self.line or self.line[0] != ":":
                raise ParserError(
                    "no colon found\n" + self._get_arounding_text(self.lineno)
                )
            self.col += 1
            obj = ColonArg(annotation=exc_cls, roles=roles)
            self._consume_descr(obj, self.indent + 1)
            args.append(obj)
        return Raises(args=args)

    def _return_like_helper(self, cls: Type[TS]) -> TS:
        value = ""  # type: str | ColonArg
        self._consume_indent()  # ensure correct indent
        line = self.line
        before, colon, after = line.partition(":")
        match = self._anno_re.match(before)
        if colon and match:
            miss = line[len(match.group()) : len(before)]
            if miss and not miss.isspace():
                raise ParserError(
                    "unrecognized things in line\n"
                    + self._get_arounding_text(self.lineno)
                )
            value = ColonArg(annotation=match.group(), roles=[], descr=after.strip())
            self.lineno += 1
        self.col = 0
        # In each case, Returns's long description indent is 4
        if isinstance(value, ColonArg):
            self._consume_descr(value, self.indent, include_short=False)
        else:
            descr_chunk = self._consume_descr(None, self.indent, include_short=False)
            value = dedent("\n".join(descr_chunk)).strip()
        return cls(value=value)

    _consume_returns = lambda self: self._return_like_helper(Returns)
    _consume_yields = lambda self: self._return_like_helper(Yields)

    def _consume_require(self) -> Require:
        descr_chunk = self._consume_descr(None, self.indent, include_short=False)
        value = dedent("\n".join(descr_chunk)).strip()
        return Require(value=value)

    def parse(self) -> Docstring:
        roles = []
        annotation = None
        descr = ""
        long_descr = ""
        match = None
        partition_lineno = self._find_first_marker()
        roles = self._consume_roles()
        self._consume_linebreaks()
        if partition_lineno is None or self.lineno < partition_lineno:
            # have description before first section
            match = self._firstline_re.match(self.line)
            if match:
                annotation, descr = match.groups()
                descr = descr.strip()
            else:
                descr = self.line.strip()
            self.lineno += 1
            self.col = 0  # descr may behind roles, so set to zero
            # join following text line into short descr
            while l := self.line:
                self.lineno += 1
                descr += l.strip()
            descr_chunk = self.lines[self.lineno : partition_lineno]
            self.lineno += len(descr_chunk)  # maybe zero
            long_descr = "\n".join(descr_chunk).strip()
        sections = []
        text_chunk: list[str] = []

        def save_text_chunk_if() -> None:
            if text_chunk:
                text = "\n".join(text_chunk).strip()
                if text:
                    sections.append(Text(value=text))
                text_chunk.clear()

        while self.lineno <= len(self.lines) - 2:  # ending is empty string
            match = self._section_marker_re.match(self.line)
            if match:
                save_text_chunk_if()
                section = self._section_dispatch(match)
                sections.append(section)
            else:
                text_chunk.append(self.line)
                self.lineno += 1
                self.col = 0
            self._consume_linebreaks()
        save_text_chunk_if()
        return Docstring(
            roles=roles,
            annotation=annotation,
            descr=descr,
            long_descr=long_descr,
            sections=sections,
        )

    def _get_arounding_text(self, lineno: int) -> str:
        builder = [
            "+ " + line if i != 2 else "> " + line
            for i, line in enumerate(self.lines[lineno - 2 : lineno + 3])
        ]
        return "\n".join(builder)


class ParserError(RuntimeError):
    ...
