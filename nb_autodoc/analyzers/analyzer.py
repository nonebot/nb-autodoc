"""Python code analyzer by parsing and analyzing AST."""

import ast
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from nb_autodoc.log import logger
from nb_autodoc.utils import TypeCheckingClass, _co_future_flags

from .definitionfinder import DefinitionFinder
from .utils import ImportFromFailed, ast_parse, eval_import_stmt


class Analyzer:
    """Wrapper of variable comment picker and overload picker.

    Args:
        name: module name
        package: package name, useful in analyzing or performing import
        path: file path to analyze
    """

    def __init__(
        self,
        name: str,
        package: Optional[str],
        path: Union[Path, str],
    ) -> None:
        self.name = name
        self.package = package
        self.path = str(path)

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)

    def exec_type_checking_body(
        self,
        body: List[ast.stmt],
        _globals: Dict[str, Any],
        _locals: Optional[Dict[str, Any]] = None,
    ) -> None:
        if _locals is None:
            _locals = _globals
        for stmt in body:
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                imports = eval_import_stmt(stmt, self.package)
                imports.update(
                    {
                        k: TypeCheckingClass.create(v.module, v.name)
                        for k, v in imports.items()
                        if isinstance(v, ImportFromFailed)
                    }
                )
                _locals.update(imports)
            else:
                flags = _co_future_flags["annotations"]
                code = compile(
                    ast.Interactive([stmt]), self.path, "single", flags=flags
                )
                exec(code, _globals, _locals)

    def analyze(self) -> None:
        code = open(self.path, "r").read()
        tree = ast_parse(code, self.path)
        visitor = DefinitionFinder(package=self.package)
        visitor.visit(tree)
        self.module = visitor.module

    # def get_autodoc_literal(self) -> Dict[str, str]:
    #     """Get `__autodoc__` using `ast.literal_eval`."""
    #     for stmt in self.tree.body:
    #         if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
    #             targets = get_assign_targets(stmt)
    #             if (
    #                 len(targets) == 1
    #                 and isinstance(targets[0], ast.Name)
    #                 and targets[0].id == "__autodoc__"
    #             ):
    #                 if stmt.value is None:
    #                     raise ValueError("autodoc requires value")
    #                 return ast.literal_eval(stmt.value)
    #     return {}
