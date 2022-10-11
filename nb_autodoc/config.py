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
    unimportable_modules: frozenset[str]
    """Module names that do not wants import, wildcard(*) is OK.

    Carefully add this option on a dependent module because we want to analyze object relationship.
    """

    ### Builder Config ###

    strict_docstring: bool
    """Apply docstring validation."""

    docstring_section_indent: Optional[int]
    """Docstring section indent. Specified from string if None."""

    exclude_modules: frozenset[str]
    """Exclude modules documentation."""


default_config: Config = frozendict(
    Config(
        unimportable_modules=frozenset(),
        strict_docstring=True,
        exclude_modules=frozenset(),
        docstring_section_indent=None,
    )
)
