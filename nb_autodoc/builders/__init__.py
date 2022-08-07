"""Builder consists of Docstring Parser, Traverser and Renderer.

Docstring Parser parse docstring to docstring tree {ref}`nb_autodoc.nodes.Docstring`.

Traverser traverse, parse and resolve the Module to {ref}`nb_autodoc.nodes.Page`.

Renderer render the {ref}`nb_autodoc.nodes.Page` to formatted text -- Markdown, reStructuredText, etc.
"""


class Builder:
    ...

    # replace ref
    # ref: r"{(?P<name>\w+?)}`(?:(?P<text>[^{}]+?) <)?(?P<content>[\w\.]+)(?(text)>)`"
