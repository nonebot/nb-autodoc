"""
Google style docstring parser.
"""
import re
import inspect
from typing import Any, Dict, Optional, List, Tuple
from enum import Enum
from textwrap import dedent

from nb_autodoc.schema import DocstringParam, DocstringSection


class _DocstringSlot(Enum):
    MODULE = 0
    VARIABLE = 1
    FUNCTION = 2
    CLASS = 3


def get_dsobj(
    s: Optional[str],
    typ: Optional[_DocstringSlot] = None,
) -> "Docstring":
    dsobj = Docstring(typ=typ)
    dsobj.parse(s or "")
    return dsobj


_SINGULAR = DocstringSection.SINGULAR
_MULTIPLE = DocstringSection.MULTIPLE
_ARGS = DocstringSection.ARGS
_RETURNS = DocstringSection.RETURNS
_ATTRIBUTES = DocstringSection.ATTRIBUTES
_RAISES = DocstringSection.RAISES
_EXAMPLES = DocstringSection.EXAMPLES
_REQUIRE = DocstringSection.REQUIRE
_VERSION = DocstringSection.VERSION
_TYPE_VERSION = DocstringSection.TYPE_VERSION
_METADATA = DocstringSection.METADATA

_sections = {
    _ARGS: {"Arguments", "Args", "Parameters", "Params", "参数"},
    _RETURNS: {"Return", "Returns", "返回"},
    _ATTRIBUTES: {"Attributes", "属性"},
    _RAISES: {"Raises", "Exceptions", "Except", "异常"},
    _EXAMPLES: {"Example", "Examples", "示例", "用法"},
    _REQUIRE: {"Require", "要求"},
    _VERSION: {"Version", "版本"},
    _TYPE_VERSION: {"TypeVersion", "类型版本"},
    _METADATA: {"Meta", "MetaData", "meta", "metadata"},
}


class Docstring:
    """
    When description include `\\n`, a short_desc is required,
    or the first line of long_desc will be thinked as short_desc.

    A section maybe ambitious (singular or multiple),
    so we define MULTIPLE as duck type rather than define MULTIPLE_OR_SINGULAR for another type.
    When match regex, we think section is multiple, else singular.
    """

    MODULE = _DocstringSlot.MODULE
    VARIABLE = _DocstringSlot.VARIABLE
    FUNCTION = _DocstringSlot.FUNCTION
    CLASS = _DocstringSlot.CLASS

    sections = _sections
    # TODO: slot attr and matcher for different docstring
    title_re = re.compile(
        "^("
        + "|".join({sec for _ in _sections.values() for sec in _})
        + r") ?(?:\((.*?)\))?:",
        flags=re.M,
    )

    def __init__(
        self,
        *,
        typ: Optional[_DocstringSlot] = None,
    ) -> None:
        self.description: str = ""
        self.args = DocstringSection(_ARGS, _MULTIPLE)
        self.returns = DocstringSection(_RETURNS, _MULTIPLE)
        self.attributes = DocstringSection(_ATTRIBUTES, _MULTIPLE)
        self.raises = DocstringSection(_RAISES, _MULTIPLE)
        self.examples = DocstringSection(_EXAMPLES, _SINGULAR)
        self.require = DocstringSection(_REQUIRE, _SINGULAR)
        self.version = DocstringSection(_VERSION, _SINGULAR)
        self.type_version = DocstringSection(_TYPE_VERSION, _SINGULAR)
        self.metadata = DocstringSection(_METADATA, _SINGULAR)
        self.patch: Dict[str, Any] = {}

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
            section: DocstringSection = getattr(self, identity.name.lower())
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
            name_re = anno_re if section.type is _RETURNS else r"[\w]+"
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
