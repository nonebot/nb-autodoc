"""Builder."""

import abc
import shutil
from pathlib import Path
from typing import Callable, Iterable, List, Union, final

from nb_autodoc.log import logger
from nb_autodoc.manager import Class, Module, ModuleManager, WeakReference
from nb_autodoc.typing import T_ClassMember, T_ModuleMember


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
    """Dict-ordered autodoc member iterator."""

    def __init__(self, module: Module) -> None:
        self.whitelist: set[str] = set()
        self.blacklist: set[str] = set()
        for name, val in module.py__autodoc__.items():
            if val:
                self.whitelist.add(name)
            else:
                self.blacklist.add(name)

    def filter(self, name: str, qualname: str) -> bool:
        return qualname in self.whitelist or not (
            name.startswith("_") or qualname in self.blacklist
        )

    def iter_module(
        self, module: Module
    ) -> Iterable[Union[T_ModuleMember, WeakReference]]:
        for dobj in module.members.values():
            if isinstance(dobj, WeakReference):
                if dobj.name in self.whitelist:
                    yield dobj
                continue
            if self.filter(dobj.name, dobj.name):
                yield dobj

    def iter_class(self, cls: Class) -> Iterable[T_ClassMember]:
        yield from filter(
            lambda dobj: self.filter(dobj.name, dobj.qualname), cls.members.values()
        )


class BuilderInterface(abc.ABC):
    @abc.abstractmethod
    def get_suffix(self) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def text(self, module: Module) -> str:
        raise NotImplementedError


class WriterMixin(BuilderInterface):
    manager: ModuleManager
    output_dir: Path

    def __init__(self) -> None:
        self.path_factory: Callable[[str, bool], List[str]]
        # Annotation here because mypy mistake attribute function

    del __init__

    @final
    def get_path(self, modulename: str, ispkg: bool) -> Path:
        mrelpath = Path(*self.path_factory(modulename, ispkg))
        path = self.output_dir / mrelpath
        if not path.is_relative_to(self.output_dir):
            raise RuntimeError(
                f"target file path '{path}' is not relative to "
                f"output dir '{self.output_dir}'"
            )
        return path.with_suffix(self.get_suffix())

    @final
    def write(self) -> None:
        modules = self.manager.modules
        top_module = modules[self.manager.name]
        # prepare top-level empty dir
        if top_module.is_package:  # skip for single module
            path = self.get_path(top_module.name, top_module.is_package)
            if path.parent.is_file():
                path.parent.unlink()
            elif path.parent.is_dir():
                logger.info(f"deleting directory {str(path.parent)!r}...")
                shutil.rmtree(path.parent)
        for module in modules.values():
            path = self.get_path(module.name, module.is_package)
            path.parent.mkdir(parents=True, exist_ok=True)
            # get documentation for each module
            docpage = self.text(module)
            path.touch(exist_ok=False)
            with open(path, "w", encoding="utf-8") as f:
                f.write(docpage)


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
        # deduplication and link definition to document

    @final
    def set_parser(self) -> None:
        ...
