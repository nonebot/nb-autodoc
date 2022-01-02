import re
import ast
import inspect
from typing import Any, cast


def convert_anno_new_style(s: str) -> str:
    "Converts type annotation to new styles."
    return MyUnparser().visit(MyTransformer().visit(ast.parse(s)))


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


class MyTransformer(ast.NodeTransformer):
    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:
        if not isinstance(node.value, ast.Name):
            return node
        result: Any = node
        name = node.value
        if name.id in ("List", "Set", "Tuple", "Dict"):
            name.id = name.id.lower()
        elif name.id == "Union":
            # slice is Tuple:
            if isinstance(node.slice, ast.Tuple):
                elts = iter(node.slice.elts)
                # make chained | expressions
                left_elt = next(elts)
                for elt in elts:
                    left_elt = ast.BinOp(
                        left=left_elt,
                        op=ast.BitOr(),
                        right=elt,
                    )
                result = left_elt
            # otherwise slice is single, do not change
        elif name.id == "Optional":
            result = ast.BinOp(
                left=node.slice,
                op=ast.BitOr(),
                right=ast.Constant(value=None),
            )
        elif name.id == "Callable":
            spec = cast(ast.Tuple, node.slice).elts
            if isinstance(spec[0], ast.List):
                params = spec[0].elts
            # args is ...
            else:
                params = [ast.Starred(value=ast.Name(id="Any")), ast.Name(id="**Any")]
            return_t = spec[1]
            result = ast.FunctionType(
                argtypes=params,
                returns=return_t,
            )
        self.generic_visit(result)
        return result


# hack to avoid ambiguities in "() -> X | Y"
# https://bugs.python.org/issue43609
class MyUnparser(ast._Unparser):  # type: ignore
    def visit_FunctionType(self, node: ast.FunctionType) -> None:
        with self.delimit("(", ")"):
            self.interleave(lambda: self.write(", "), self.traverse, node.argtypes)
        self.write(" -> ")
        # add paren when return type is a union (bit or)
        need_paren = isinstance(node.returns, ast.BinOp) and isinstance(
            node.returns.op, ast.BitOr
        )
        with self.delimit_if("(", ")", need_paren):
            self.traverse(node.returns)
