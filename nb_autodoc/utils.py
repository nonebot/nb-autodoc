import ast
import re
import enum
import inspect
from typing import Any, List, Optional
from inspect import Signature, Parameter

from nb_autodoc.pycode.unparser import unparse


def convert_anno_new_style(s: str) -> str:
    "Converts type annotation to new styles."
    # noqa: change pattern of unparser is not good idea
    return unparse(ast.parse(s).body[0], anno_new_style=True).strip()


def formatannotation(annot: type, new_style: bool = True) -> str:
    """
    Format annotation.

    Handle NewType, ForwardRef.

    Args:
        new_style: convert annotation to py3.10 new style
    """
    if annot is inspect.Parameter.empty:
        return ""
    elif annot is type(None) or annot is None:
        return "None"
    elif isinstance(annot, str):
        # annot in a bare string, just return it
        return annot
    module = getattr(annot, "__module__", "")
    if module == "typing" and getattr(annot, "__qualname__", "").startswith("NewType."):
        return annot.__name__
    elif module.startswith("nptyping."):
        return repr(annot)
    formatted = inspect.formatannotation(annot)
    if new_style:
        formatted = convert_anno_new_style(formatted)
    # annot string in class subscript will construct a ForwardRef
    formatted = re.sub(
        r"\b(typing\.)?ForwardRef\((?P<quot>[\"\'])(?P<str>.*?)(?P=quot)\)",
        r"\g<str>",
        formatted,
    )
    return formatted


def get_signature(obj: Any) -> Signature:
    """Wrapper of `inspect.signature`."""
    if hasattr(obj, "__signature__"):
        return obj.__signature__
    try:
        return inspect.signature(obj)
    except Exception:
        if inspect.isclass(obj):
            if issubclass(obj, (Exception, type)):
                return Signature()
            for cls in obj.__bases__:
                if obj.__init__ is cls.__init__ and cls.__module__ == "builtins":
                    return Signature()
    return inspect.signature(obj)


def signature_repr(sig: Signature, returns: Optional[List[str]] = None) -> str:
    """
    Represent inspect.Signature without annotation.

    Properly solve the Parameter default value represent.
    But do not show return annotation. (which cause a redudant output)

    Args:
        sig: a signature object
        returns: if given, then represent params with returns
    """

    def safe_default_value(p: Parameter) -> Parameter:
        value = p.default
        if value is Parameter.empty:
            return p

        replacement = None
        if isinstance(value, enum.Enum):
            replacement = str(value)
        elif value is Ellipsis:
            replacement = "..."
        elif inspect.isclass(value):
            replacement = value.__name__
        elif " at 0x" in repr(value):
            replacement = re.sub(r" at 0x\w+", "", repr(value))

        if replacement:

            class mock:
                def __repr__(self) -> str:
                    return replacement  # type: ignore

            return p.replace(default=mock())
        return p

    # Duplicated from `inspect.Signature.__str__`, remove all annotation
    result = []
    render_pos_only_separator = False
    render_kw_only_separator = True
    for param in sig.parameters.values():
        param = safe_default_value(param)
        param = param.replace(annotation=Parameter.empty)
        formatted = str(param)

        kind = param.kind

        if kind == Parameter.POSITIONAL_ONLY:
            render_pos_only_separator = True
        elif render_pos_only_separator:
            result.append("/")
            render_pos_only_separator = False

        if kind == Parameter.VAR_POSITIONAL:
            render_kw_only_separator = False
        elif kind == Parameter.KEYWORD_ONLY and render_kw_only_separator:
            result.append("*")
            render_kw_only_separator = False

        result.append(formatted)

    if render_pos_only_separator:
        result.append("/")

    rendered = "({})".format(", ".join(result))

    if returns:
        rendered += " -> {}".format(" | ".join(returns))

    return rendered
