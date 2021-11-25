import ast
from typing import Union

from nb_autodoc.pycode.annotransformer import convert_anno_new_style


def get_returns(node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> str:
    if node.returns:
        return convert_anno_new_style(ast.unparse(node.returns))
    else:
        return ""
