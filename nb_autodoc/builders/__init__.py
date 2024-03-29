"""Builder."""

import abc
import shutil
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple
from typing_extensions import final

from nb_autodoc.log import logger
from nb_autodoc.manager import Class, ImportRef, Module, ModuleManager, Variable
from nb_autodoc.typing import T_ClassMember, T_Definition, T_ModuleMember

default_slugify = lambda dobj: None


def default_path_factory(modulename: str, ispkg: bool) -> List[str]:
    """Default module path constructor.

    Returns ('foo','bar') if 'foo.bar' is module at 'foo/bar.py'.
    Returns ('foo','bar','index') if 'foo.bar' is package at 'foo/bar/__init__.py'.
    """
    pparts = modulename.split(".")
    if ispkg:
        pparts.append("index")
    return pparts


# TODO: auto generation docref for reexport which is not whitelisted
# so called `conventional import list`
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

    def is_whitelisted(self, qualname: str) -> bool:
        return qualname in self.whitelist

    def is_blacklisted(self, qualname: str) -> bool:
        return qualname.rpartition(".")[2].startswith("_") or qualname in self.blacklist

    def iter_module(self, module: Module) -> Iterable[T_ModuleMember]:
        for dobj in module.members.values():
            if isinstance(dobj, ImportRef):
                if dobj.name in self.whitelist:
                    ref_found = dobj.find_definition()
                    if ref_found:
                        yield ref_found
            elif self.is_whitelisted(dobj.qualname):
                yield dobj
            elif isinstance(dobj, Variable) and not dobj.doctree:
                pass
            elif not self.is_blacklisted(dobj.qualname):
                yield dobj

    def iter_class(self, cls: Class) -> Iterable[T_ClassMember]:
        # in case class is reference from other module (reexport), then
        # other module's `__autodoc__` for this class is invalid
        for dobj in cls.members.values():
            if self.is_whitelisted(dobj.qualname):
                yield dobj
            elif isinstance(dobj, Variable) and not dobj.doctree:
                pass
            elif not self.is_blacklisted(dobj.qualname):
                yield dobj

    def _iter_all_definitions(self, module: Module) -> Iterable[T_Definition]:
        for dobj in self.iter_module(module):
            yield dobj
            if isinstance(dobj, Class):
                yield from self.iter_class(dobj)


class Builder(abc.ABC):
    """Builder store the context of all modules."""

    def __init__(self, manager: ModuleManager) -> None:
        # Args:
        #     linkable_deepth: Positive integer. The max length of common path prefix
        #         in calculating relative path. Raise if the prefixs do not equal.
        #         By default, it is the length of output_dir + 1, such as
        #         2 for `build/pkg` or `build/pkg/subpkg`.
        self.manager = manager
        # setting some lazy config
        self.output_dir = Path(manager.config["output_dir"])
        self.write_encoding = manager.config["write_encoding"]
        # get documentable modules and paths
        skip_doc_modules = list(manager.config["exclude_documentation_modules"])
        path_factory = manager.config["path_factory"]
        member_iterator_cls = manager.config["member_iterator_cls"]
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
        # redirect ref's module for correct link
        self._documented: set[T_Definition] = set()
        self._module_locator: dict[T_Definition, Module] = {}
        self.anchors: dict[T_Definition, str] = {}
        """The URL anchor (slug) for linkable objects."""
        self.slugify = self.get_slugify_impl()
        """The generic function implement the URL slug creator."""
        self._traverse_all_definitions()

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

    def _traverse_all_definitions(self) -> None:
        for module, miterator in self._member_iterators.items():
            for dobj in miterator._iter_all_definitions(module):
                if dobj.module is not module:
                    self._module_locator[dobj] = module
                anchor = self.slugify(dobj)
                if anchor is not None:
                    self.anchors[dobj] = anchor
            # just notice module member reduplicated document (class will cause big log)
            for dobj in miterator.iter_module(module):
                if dobj not in self._documented:
                    self._documented.add(dobj)
                else:
                    logger.warning(
                        f"object {dobj.fullname!r} is already documented "
                        f"at {self.get_anchor_ref(dobj)}"
                    )

    def get_anchor_ref(self, dobj: T_Definition) -> Tuple[str, Optional[str]]:
        module = self._module_locator.get(dobj) or dobj.module
        anchor = self.anchors.get(dobj)
        return (module.name, anchor)

    def get_slugify_impl(self) -> Callable[[T_Definition], Optional[str]]:
        # by default all resource is unlinkable
        return default_slugify

    def get_member_iterator(self, module: Module) -> MemberIterator:
        return self._member_iterators[module]

    @final
    def write(self) -> None:
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
            doc = self.text(self.modules[modname])
            path.touch(exist_ok=False)
            path.write_text(doc, encoding=self.write_encoding)

    @abc.abstractmethod
    def get_suffix(self) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def text(self, module: Module) -> str:
        raise NotImplementedError
