"""
Google style docstring parser.
"""
import re
import inspect
from typing import Any, Dict, Literal, Set, Optional, List, Tuple
from enum import IntEnum
from textwrap import dedent

from nb_autodoc.schema import DocstringParam, DocstringSection


ARGS = "args"
RETURNS = "returns"
ATTRIBUTES = "attributes"
RAISES = "raises"
EXAMPLES = "examples"
REQUIRE = "require"
VERSION = "version"
TYPE_VERSION = "type_version"

_sections = {
    ARGS: {"Arguments", "Args", "Parameters", "Params", "参数"},
    RETURNS: {"Return", "Returns", "返回"},
    ATTRIBUTES: {"Attributes", "属性"},
    RAISES: {"Raises", "Exceptions", "Except", "异常"},
    EXAMPLES: {"Example", "Examples", "示例", "用法"},
    REQUIRE: {"Require", "要求"},
    VERSION: {"Version", "版本"},
    TYPE_VERSION: {"TypeVersion", "类型版本"},
}


def get_sections(names: Set[str]) -> Dict[str, Set[str]]:
    return {k: v for k, v in _sections.items() if k in names}


def get_dsobj(
    s: Optional[str],
    typ: Optional[Literal["variable", "function", "class"]] = None,
) -> "Docstring":
    dsobj = Docstring(typ=typ)
    dsobj.parse(s or "")
    return dsobj


class _SectionKind(IntEnum):
    SINGULAR = 0
    MULTIPLE = 1


_SINGULAR = _SectionKind.SINGULAR
_MULTIPLE = _SectionKind.MULTIPLE


class Docstring:
    """
    When description include `\\n`, a short_desc is required,
    or the first line of long_desc will be thinked as short_desc.

    A section maybe ambitious (singular or multiple),
    so we define MULTIPLE as duck type rather than define MULTIPLE_OR_SINGULAR for another type.
    When match regex, we think section is multiple, else singular.
    """

    SINGULAR = _SectionKind.SINGULAR
    MULTIPLE = _SectionKind.MULTIPLE

    sections = _sections
    title_re = re.compile(
        "^("
        + "|".join({sec for _ in _sections.values() for sec in _})
        + r") ?(?:\((.*?)\))?:",
        flags=re.M,
    )

    def __init__(
        self,
        *,
        typ: Optional[Literal["variable", "function", "class"]] = None,
    ) -> None:
        self.short_desc: str = ""
        self.long_desc: str = ""
        self.description: str = ""
        self.args = DocstringSection(ARGS, kind=_MULTIPLE)
        self.returns = DocstringSection(RETURNS, kind=_MULTIPLE)
        self.attributes = DocstringSection(ATTRIBUTES, kind=_MULTIPLE)
        self.raises = DocstringSection(RAISES, kind=_MULTIPLE)
        self.examples = DocstringSection(EXAMPLES, kind=_SINGULAR)
        self.require = DocstringSection(REQUIRE, kind=_SINGULAR)
        self.version = DocstringSection(VERSION, kind=_SINGULAR)
        self.type_version = DocstringSection(TYPE_VERSION, kind=_SINGULAR)
        self.patch: Dict[str, Any] = {}
        if typ == "variable":
            for id in _sections.keys() - {
                "examples",
                "require",
                "version",
                "type_version",
            }:
                delattr(self, id)
        elif typ == "function":
            for id in _sections.keys() - {
                "args",
                "returns",
                "raises",
                "examples",
                "require",
                "version",
            }:
                delattr(self, id)
        elif typ == "class":
            for id in _sections.keys() - {
                "args",
                "attributes",
                "examples",
                "require",
                "version",
            }:
                delattr(self, id)

    def parse(self, docstring: str) -> None:
        docstring = inspect.cleandoc(docstring)
        if not docstring:
            return
        matches = list(self.title_re.finditer(docstring))
        desc_chunk = docstring[: matches[0].start()] if matches else docstring
        desc_chunk = desc_chunk.strip()
        desc_parts = [i.strip() for i in desc_chunk.split("\n", 1)]
        self.short_desc = self.description = desc_parts[0]
        if len(desc_parts) == 2:
            self.long_desc = desc_parts[1]
            self.description += f"\n\n{self.long_desc}"
        if not matches:
            return
        splits: List[Tuple[str, slice]] = []  # raw text sections
        for i in range(len(matches) - 1):
            splits.append(
                (matches[i].group(1), slice(matches[i].end(), matches[i + 1].start()))
            )
        splits.append((matches[-1].group(1), slice(matches[-1].end(), None)))
        for i, (name, seg) in enumerate(splits):
            identity = None
            # find identity
            for _id, _aliases in self.sections.items():
                if name in _aliases:
                    identity = _id
            if identity is None:
                continue
            text = inspect.cleandoc(docstring[seg])
            section = getattr(self, identity)
            section.version = matches[i].group(2)
            section.source = text
            self.generic_parse(section)

    def generic_parse(self, section: DocstringSection) -> None:
        method = getattr(self, "parse_" + section.identity, None)
        if method is not None:
            try:
                method(section)
            except Exception:
                print(
                    "Error parsing docstring: "
                    f"find method {method.__name__!r} but raises during running."
                )
        else:
            if section.kind == _SINGULAR:
                return

            def parse_roles(s: str) -> List[DocstringParam.Role]:
                return [
                    DocstringParam.Role(match.group(1), match.group(2))
                    for match in re.finditer(r"{([\w]+)}`(.*?)`", s)
                ]

            anno_re = r"[\w\.\[\], ]+"
            name_re = anno_re if section.identity == RETURNS else r"[\w]+"
            line_re = r"^({name})(?: *\(({anno})\))?(.*?):".format(  # noqa
                name=name_re, anno=anno_re
            )
            matches = list(re.finditer(line_re, section.source, flags=re.M))
            if not matches:
                return
            descriptions: List[str] = []
            for i in range(len(matches) - 1):
                descriptions.append(
                    section.source[matches[i].end() : matches[i + 1].start()]
                )
            descriptions.append(section.source[matches[-1].end() :])
            for i, description in enumerate(descriptions):
                description, long_description = (description + "\n").split("\n", 1)
                section.content.append(
                    DocstringParam(
                        name=matches[i].group(1),
                        annotation=matches[i].group(2),
                        roles=parse_roles(matches[i].group(3)),
                        description=description.strip(),
                        long_description=dedent(long_description).strip(),
                    )
                )
