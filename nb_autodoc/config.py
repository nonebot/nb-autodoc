from __future__ import annotations

from typing import TypedDict

from nb_autodoc.utils import frozendict


class Config(TypedDict, total=False):
    """Config for Module. Default to {ref}`.default_config`."""

    # Config is composed of two parts: Manager config and Builder config

    ### Manager Config ###

    # # future
    # static: bool
    # """Fully static code analysis."""

    # used by ModuleFinder
    skip_import_modules: set[str] | frozenset[str]
    """Module names that skip importation and analysis.

    Carefully add this option on a dependent module because we want to
    analyze python object relationship.

    Support `fnmatch` pattern, such as '*', '?', etc.
    """

    ### Builder Config ###

    strict_docstring: bool
    """Apply docstring validation."""

    docstring_section_indent: int | None
    """Docstring section indent. Specified from string if None."""

    exclude_documentation_modules: set[str] | frozenset[str]
    """Exclude documentation modules.

    Support `fnmatch` pattern, such as '*', '?', etc.
    """

    write_encoding: str
    """The file encoding to write."""


default_config: Config = frozendict(
    Config(
        skip_import_modules=frozenset(),
        strict_docstring=True,
        docstring_section_indent=None,
        exclude_documentation_modules=frozenset(),
        write_encoding="utf-8",
    )
)

# check total key for default_config
assert default_config.keys() == Config.__annotations__.keys()
