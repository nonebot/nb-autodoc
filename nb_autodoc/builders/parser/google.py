"""
Google style docstring parser.
"""
import re
import inspect
from typing import Any, Dict, Literal, Set, Optional, List, Tuple

from nb_autodoc.schema import DocstringSection, DocstringParam


_MULTIPLE = DocstringSection
_SINGULAR = Optional[str]


def get_sections(names: Set[str]) -> Dict[str, Set[str]]:
    return {k: v for k, v in Docstring._sections.items() if k in names}


def get_dsobj(
    s: Optional[str],
    typ: Optional[Literal["variable", "function", "class"]] = None,
) -> "Docstring":
    dsobj = Docstring(typ=typ)
    dsobj.parse(s or "")
    return dsobj


class Docstring:
    """
    When description include `\\n`, a short_desc is required,
    or the first line of long_desc will be thinked as short_desc.

    A section maybe ambitious (singular_or_multiple),
    so we define duck type rather than define MULTIPLE_OR_SINGULAR for another type hints.
    When match regex, we think section is multiple, or singular.
    """

    MULTIPLE = _MULTIPLE
    SINGULAR = _SINGULAR

    _sections = {
        "args": {"Arguments", "Args", "Parameters", "Params", "参数"},
        "returns": {"Return", "Returns", "返回"},
        "attributes": {"Attributes", "属性"},
        "raises": {"Raises", "Exceptions", "Except", "异常"},
        "examples": {"Example", "Examples", "示例", "用法"},
        "require": {"Require", "要求"},
        "version": {"Version", "版本"},
        "type_version": {"TypeVersion", "类型版本"},
    }
    _sections_variable = get_sections(
        {"examples", "require", "version", "type_version"}
    )
    _sections_function = get_sections(
        {"args", "returns", "raises", "examples", "require", "version"}
    )
    _sections_class = get_sections(
        {"args", "attributes", "examples", "require", "version"}
    )
    __slots__ = (
        "sections",
        "short_desc",
        "long_desc",
        "description",
        *_sections.keys(),
        "patch",
    )
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
        # control visitor in different object's docstring
        self.sections: Dict[str, Set[str]] = getattr(
            Docstring, "_sections" + (f"_{typ}" if typ else "")
        )
        self.short_desc: str = ""
        self.long_desc: str = ""
        self.description: str = ""
        self.args: _MULTIPLE = DocstringSection("args", content=[])
        self.returns: _MULTIPLE = DocstringSection("returns", content=[])
        self.attributes: _MULTIPLE = DocstringSection("attributes", content=[])
        self.raises: _MULTIPLE = DocstringSection("raises", content=[])
        self.examples: _SINGULAR = None
        self.require: _MULTIPLE = DocstringSection("require", content=[])
        self.version: _SINGULAR = None
        self.type_version: _SINGULAR = None
        self.patch: Dict[str, Any] = {}

    def parse(self, text: str) -> None:
        text = inspect.cleandoc(text)
        if not text:
            return
        matches = list(self.title_re.finditer(text))
        desc_chunk = text[: matches[0].start()] if matches else text
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
            for identity, set_ in self.sections.items():
                if not name in set_:
                    continue
                text_seg = inspect.cleandoc(text[seg])
                section = getattr(self, identity)
                if section is None:
                    setattr(self, identity, text_seg)
                    continue
                elif isinstance(section, DocstringSection):
                    section.version = matches[i].group(2)
                    section.source = text_seg
                else:
                    continue
                # try to call self-defined method
                method = getattr(self, "parse_" + identity, None)
                if method is not None and callable(method):
                    try:
                        method()
                    except Exception:
                        print(
                            "Error parsing docstring: "
                            f"find method {method.__name__!r} but raises when calling.",
                        )
                else:
                    self.generic_parser(section)

    @staticmethod
    def _parse_params(
        s: str, *, argument_regex: Optional[str] = None
    ) -> List[DocstringParam]:
        """
        Parse text to list of DocstringParam if match regex.
        """
        _regex = r"^({argument}) ?(?:\((.*?)\))?:"
        regex = _regex.format(argument=argument_regex or r"[a-zA-Z0-9_]+")
        result: List[DocstringParam] = []
        matches = list(re.finditer(regex, s, flags=re.M))
        if not matches:
            return []
        splits: List[Tuple[str, str]] = []
        for i in range(len(matches) - 1):
            splits.append(
                (matches[i].group(1), s[matches[i].end() : matches[i + 1].start()])
            )
        splits.append((matches[-1].group(1), s[matches[-1].end() :]))
        for i, (name, desc) in enumerate(splits):
            result.append(
                DocstringParam(
                    name=name,
                    version=matches[i].group(2),
                    description=re.sub(r"\n[ ]*", " ", desc).strip(),
                )
            )
        return result

    def generic_parser(self, section: DocstringSection) -> None:
        text = section.source
        if not isinstance(text, str):
            return
        params = self._parse_params(text)
        if params:
            section.content = params

    def parse_returns(self) -> None:
        text = self.returns.source
        params = self._parse_params(text, argument_regex=r"[a-zA-Z0-9_\[\]]+")
        if params:
            self.returns.content = params
