"""
Google style docstring parser.
"""
import re
import inspect
from typing import Any, Dict, Literal, Optional, List, Tuple
from enum import Enum
from textwrap import dedent

from nb_autodoc.schema import DocstringParam, DocstringSection


def get_dsobj(
    s: Optional[str],
    typ: Optional[Literal["variable", "function", "class"]] = None,
) -> "Docstring":
    dsobj = Docstring(typ=typ)
    dsobj.parse(s or "")
    return dsobj


class _SectionKind(Enum):
    SINGULAR = 0
    MULTIPLE = 1


class _SectionType(Enum):
    ARGS = 0
    RETURNS = 1
    ATTRIBUTES = 2
    RAISES = 3
    EXAMPLES = 4
    REQUIRE = 5
    VERSION = 6
    TYPE_VERSION = 7


_SINGULAR = _SectionKind.SINGULAR
_MULTIPLE = _SectionKind.MULTIPLE

_sections = {
    _SectionType.ARGS: {"Arguments", "Args", "Parameters", "Params", "参数"},
    _SectionType.RETURNS: {"Return", "Returns", "返回"},
    _SectionType.ATTRIBUTES: {"Attributes", "属性"},
    _SectionType.RAISES: {"Raises", "Exceptions", "Except", "异常"},
    _SectionType.EXAMPLES: {"Example", "Examples", "示例", "用法"},
    _SectionType.REQUIRE: {"Require", "要求"},
    _SectionType.VERSION: {"Version", "版本"},
    _SectionType.TYPE_VERSION: {"TypeVersion", "类型版本"},
}


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
    SectionType = _SectionType
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
        self.description: str = ""
        self.args = DocstringSection(_SectionType.ARGS, _MULTIPLE)
        self.returns = DocstringSection(_SectionType.RETURNS, _MULTIPLE)
        self.attributes = DocstringSection(_SectionType.ATTRIBUTES, _MULTIPLE)
        self.raises = DocstringSection(_SectionType.RAISES, _MULTIPLE)
        self.examples = DocstringSection(_SectionType.EXAMPLES, _SINGULAR)
        self.require = DocstringSection(_SectionType.REQUIRE, _SINGULAR)
        self.version = DocstringSection(_SectionType.VERSION, _SINGULAR)
        self.type_version = DocstringSection(_SectionType.TYPE_VERSION, _SINGULAR)
        self.patch: Dict[str, Any] = {}
        section_keys = {s.name.lower() for s in _sections.keys()}
        if typ == "variable":
            for id in section_keys - {
                "examples",
                "require",
                "version",
                "type_version",
            }:
                delattr(self, id)
        elif typ == "function":
            for id in section_keys - {
                "args",
                "returns",
                "attributes",
                "raises",
                "examples",
                "require",
                "version",
            }:
                delattr(self, id)
        elif typ == "class":
            for id in section_keys - {
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
        if not matches:
            self.description = docstring.strip()
            return
        self.description = docstring[: matches[0].start()].strip()
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
            text = dedent(docstring[seg]).strip()
            section = getattr(self, identity.name.lower())
            section.version = matches[i].group(2)
            section.source = text
            self.generic_parse(section)

    def generic_parse(self, section: DocstringSection) -> None:
        method = getattr(self, "parse_" + section.type.name.lower(), None)
        if method is not None:
            try:
                method(section)
            except Exception:
                print(
                    "Error parsing docstring: "
                    f"find method {method.__name__!r} but raises during running."
                )
        else:
            if section.kind is _SINGULAR:
                return

            def parse_roles(s: str) -> List[DocstringParam.Role]:
                return [
                    DocstringParam.Role(match.group(1), match.group(2))
                    for match in re.finditer(r"{([\w]+)}`(.*?)`", s)
                ]

            anno_re = r"[\w\.\[\], ]+"
            name_re = anno_re if section.type is _SectionType.RETURNS else r"[\w]+"
            line_re = r"^(?! )({name})(?: *\(({anno})\))?(.*?):".format(  # noqa
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
                # self splitor rather than inspect.cleandoc
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
