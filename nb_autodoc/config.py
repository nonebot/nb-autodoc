from typing import Optional, TypedDict

from nb_autodoc.utils import frozendict


class Config(TypedDict):
    """Config for Module. Default to {ref}`.default_config`."""

    # Config is composed of two parts: Manager config and Builder config

    ### Manager Config ###

    # # future
    # static: bool
    # """Fully static code analysis."""

    # Filter pattern for finder
    skip_import_modules: frozenset[str]
    """Module names that skip importation and analysis, wildcard(*) is OK.

    Carefully add this option on a dependent module because we want to
    analyze python object relationship.
    """

    ### Builder Config ###

    strict_docstring: bool
    """Apply docstring validation."""

    docstring_section_indent: Optional[int]
    """Docstring section indent. Specified from string if None."""

    builder_exclude_modules: frozenset[str]
    """Exclude modules documentation."""


default_config: Config = frozendict(
    Config(
        skip_import_modules=frozenset(),
        strict_docstring=True,
        docstring_section_indent=None,
        builder_exclude_modules=frozenset(),
    )
)
