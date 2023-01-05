"""Builder."""

import abc
from pathlib import Path
from typing import Callable, Dict, Union, final, List

from nb_autodoc.manager import Class, Function, ModuleManager, Variable


def default_path_factory(modulename: str, ispkg: bool) -> List[str]:
    """Default module path constructor.

    Returns ('foo','bar') if 'foo.bar' is module at 'foo/bar.py'.
    Returns ('foo','bar','index') if 'foo.bar' is package at 'foo/bar/__init__.py'.
    """
    pparts = modulename.split(".")
    if ispkg:
        pparts.append("index")
    return pparts


class MemberIterator:
    ...


class BuilderInterface(abc.ABC):
    @abc.abstractmethod
    def get_suffix(self) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def text(self, itor: MemberIterator) -> str:
        raise NotImplementedError


class WriterMixin(BuilderInterface):
    manager: ModuleManager
    output_dir: Path

    def __init__(self) -> None:
        self.path_factory: Callable[[str, bool], List[str]]
        # Annotation here because mypy mistake attribute function

    del __init__

    @final
    def write(self) -> None:
        modules = self.manager.modules
        for name in sorted(modules.keys()):
            module = modules[name]
            # sort by module name because
            # get module filepath
            mpath = Path(*self.path_factory(module.name, module.prime_py.is_package))
            path = self.output_dir / mpath
            if not path.is_relative_to(self.output_dir):
                raise RuntimeError(
                    f"target file path {path!r} is not relative to "
                    f"output dir {self.output_dir!r}"
                )
            path = path.with_suffix(self.get_suffix())
            # get iterator and call text


class Builder(WriterMixin, BuilderInterface):
    @final
    def __init__(
        self,
        manager: ModuleManager,
        *,
        output_dir: Union[str, Path] = "build",
        path_factory: Callable[[str, bool], List[str]] = default_path_factory,
    ) -> None:
        self.manager = manager
        self.output_dir = Path(output_dir)
        self.path_factory = path_factory
        self.filters: list[Callable[[str], bool]] = []
        self.filters.append(lambda x: x in {} or not (x.startswith("_") or x in {}))
        # deduplication and link definition to document

    @final
    def filter(self, name: str) -> bool:
        allow = True
        for f in self.filters:
            allow = f(name)
            if not allow:
                allow = False
                break
        return allow

    @final
    def add_filter(self, func: Callable[[str], bool]) -> None:
        self.filters.append(func)

    @final
    def set_parser(self) -> None:
        ...

    @final
    def set_member_refiner(self, conf: Dict[str, None]) -> None:
        ...

    @final
    def iter_members(self) -> MemberIterator:
        ...
