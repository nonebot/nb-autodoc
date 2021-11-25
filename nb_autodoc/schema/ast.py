import ast
from typing import Union
from dataclasses import dataclass
from inspect import Signature


@dataclass
class OverloadFunctionDef:
    ast: Union[ast.FunctionDef, ast.AsyncFunctionDef]
    signature: Signature
    docstring: str
