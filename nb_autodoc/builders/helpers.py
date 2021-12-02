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
        if inspect.ismethod(dobj.obj):
            prefix_builder.append("method")
        elif inspect.iscoroutinefunction(dobj.obj):
            prefix_builder.append("async def")
        else:
            prefix_builder.append("def")
        body += dobj.params()
    elif isinstance(dobj, Variable):
        if is_property(dobj.obj):
            prefix_builder.append("property")
        elif dobj.cls is None:
            prefix_builder.append("var")
        else:
            prefix_builder.append(
                "instance-var" if dobj.is_instance_var else "class-var"
            )
    elif isinstance(dobj, LibraryAttr):
        prefix_builder.append("library-attr")
    prefix = " ".join(prefix_builder)
    return f"_{prefix}_ `{body}`"
