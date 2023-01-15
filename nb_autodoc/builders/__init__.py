"""Builder."""

import abc
import shutil
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Type, Union, final

from nb_autodoc.log import logger
from nb_autodoc.manager import Class, ImportRef, Module, ModuleManager
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

    def iter_module(self, module: Module) -> Iterable[T_ModuleMember]:
        for dobj in module.members.values():
            if isinstance(dobj, ImportRef):
                if dobj.name in self.whitelist:
                    yield dobj.find_definition()
            elif self.filter(dobj.name, dobj.name):
                yield dobj

    def iter_class(self, cls: Class) -> Iterable[T_ClassMember]:
        # in case class is reference from other module (reexport), then
        # other module's `__autodoc__` for this class is invalid
        yield from filter(
            lambda dobj: self.filter(dobj.name, dobj.qualname), cls.members.values()
        )


class Builder(abc.ABC):
    """Builder store the context of all modules."""

    def __init__(
        self,
        manager: ModuleManager,
        *,
        output_dir: Union[str, Path] = "build",
        path_factory: Optional[Callable[[str, bool], List[str]]] = None,
        member_iterator_cls: Optional[Type[MemberIterator]] = None,
    ) -> None:
        # Args:
        #     linkable_deepth: Positive integer. The max length of common path prefix
        #         in calculating relative path. Raise if the prefixs do not equal.
        #         By default, it is the length of output_dir + 1, such as
        #         2 for `build/pkg` or `build/pkg/subpkg`.
        self.manager = manager
        self.output_dir = Path(output_dir)
        # get documentable modules and paths
        skip_doc_modules = list(self.manager.config["exclude_documentation_modules"])
        exclude_module = lambda x: any(fnmatchcase(x, pt) for pt in skip_doc_modules)
        if path_factory is None:
            path_factory = default_path_factory
        self.modules: dict[str, Module] = {}
        self.paths: dict[str, Path] = {}
        for module in self.manager.modules.values():
            if exclude_module(module.name):
                continue
            self.modules[module.name] = module
            self.paths[module.name] = self._build_path(
                module.name, module.is_package, path_factory
            )
        # get member iterators for modules
        if member_iterator_cls is None:
            member_iterator_cls = MemberIterator
        self._member_iterators = {
            module: member_iterator_cls(module) for module in self.modules.values()
        }
        # traverse all members to create anchor

    def _build_path(
        self,
        modulename: str,
        ispkg: bool,
        path_factory: Callable[[str, bool], List[str]],
    ) -> Path:
        mrelpath = Path(*path_factory(modulename, ispkg))
        # '..' and '.' is not allowed while doing relative link, but we dont check
        path = self.output_dir / mrelpath
        return path.with_suffix(self.get_suffix())

    def get_member_iterator(self, module: Module) -> MemberIterator:
        return self._member_iterators[module]

    @final
    def write(self) -> None:
        modules = self.manager.modules
        # prepare top-level empty dir
        if not self.manager.is_single_module:  # skip for single module
            path = self.paths[min(self.paths)]
            if path.parent.is_file():
                path.parent.unlink()
            elif path.parent.is_dir():
                logger.info(f"deleting directory {str(path.parent)!r}...")
                shutil.rmtree(path.parent)
        for modname, path in self.paths.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            doc = self.text(modules[modname])
            path.touch(exist_ok=False)
            path.write_text(doc, encoding=self.manager.config["write_encoding"])

    @abc.abstractmethod
    def get_suffix(self) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def text(self, module: Module) -> str:
        raise NotImplementedError
