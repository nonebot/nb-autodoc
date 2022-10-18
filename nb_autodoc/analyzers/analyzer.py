import ast
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from nb_autodoc.log import logger

from .definitionfinder import DefinitionFinder
from .utils import (
    ImportFailed,
    ast_parse,
    eval_import_stmts,
    get_assign_targets,
    get_constant_value,
    is_constant_node,
)


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

        code = open(self.path, "r").read()
        self.tree = ast_parse(code, self.path)

        self.type_checking_imported: Optional[Dict[str, Any]] = None
        self.type_checking_failed: Optional[Dict[str, ImportFailed]] = None
        self._first_traverse_module()

        self.analyze()

    @property
    def filename(self) -> str:
        return Path(self.path).name

    def analyze(self) -> None:
        visitor = DefinitionFinder(self.name, self.package)
        visitor.visit(self.tree)
        self.definitions = visitor.definitions
        self.externals = visitor.externals
        self.var_comments = visitor.var_comments
        self.type_comments = visitor.type_comments
        self.annotations = visitor.annotations

    def _first_traverse_module(self) -> None:
        """Find module metadata like `TYPE_CHECKING` or `from __future__ import ...`."""
        type_checking_body: Optional[List[ast.stmt]] = None
        for stmt in self.tree.body:
            if isinstance(stmt, ast.If):
                # handle TYPE_CHECKING
                if (
                    isinstance(stmt.test, ast.Name) and stmt.test.id == "TYPE_CHECKING"
                ) or (
                    is_constant_node(stmt.test)
                    and get_constant_value(stmt.test) == False
                ):
                    # TODO: Name is not resolved, only literal check
                    if is_constant_node(stmt.test):
                        logger.warning(
                            f"use TYPE_CHECKING instead of False",
                            (self.filename, stmt.lineno),
                        )
                    if type_checking_body is None:
                        type_checking_body = stmt.body.copy()
                    else:
                        type_checking_body.extend(stmt.body)
        if type_checking_body is not None:
            self.type_checking_imported, self.type_checking_failed = eval_import_stmts(
                type_checking_body
            )

    def get_autodoc_literal(self) -> Dict[str, str]:
        """Get `__autodoc__` using `ast.literal_eval`."""
        for stmt in self.tree.body:
            if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                targets = get_assign_targets(stmt)
                if (
                    len(targets) == 1
                    and isinstance(targets[0], ast.Name)
                    and targets[0].id == "__autodoc__"
                ):
                    if stmt.value is None:
                        raise ValueError("autodoc requires value")
                    return ast.literal_eval(stmt.value)
        return {}
