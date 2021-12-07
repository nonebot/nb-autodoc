import inspect
from typing import Union

from nb_autodoc import Class, Function, Variable, LibraryAttr


def is_property(obj: object) -> bool:
    return isinstance(obj, property)


def get_title(dobj: Union[Class, Function, Variable, LibraryAttr]) -> str:
    """
    Get a simple title of documentation object.

    Example:
        ```python
        async def foo(a: int, *, b, **kwargs) -> str:
            ...
        ```
        -> `_async def_ foo(a, *, b, **kwargs)`
    """
    prefix_builder = []
    body = dobj.name
    if isinstance(dobj, Class):
        if inspect.isabstract(dobj.obj):
            prefix_builder.append("abstract")
        prefix_builder.append("class")
        body += dobj.params()
    elif isinstance(dobj, Function):
        if inspect.isabstract(dobj.obj):
            prefix_builder.append("abstract")
        prefix_builder.append(dobj.functype)
        body += dobj.params()
    elif isinstance(dobj, Variable):
        if is_property(dobj.obj):
            prefix_builder.append("property")
        else:
            prefix_builder.append(dobj.vartype)
    elif isinstance(dobj, LibraryAttr):
        prefix_builder.append("library-attr")
    prefix = " ".join(prefix_builder)
    return f"_{prefix}_ `{body}`"
