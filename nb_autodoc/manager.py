"""Inspect and analyze module from runtime and AST."""

from __future__ import annotations as _

from collections import ChainMap, defaultdict
from contextvars import ContextVar
from enum import Enum
from types import BuiltinFunctionType, FunctionType, ModuleType
from typing import Any, Mapping, NamedTuple, TypeVar, cast
from typing_extensions import Literal

from nb_autodoc.analyzers.analyzer import Analyzer
from nb_autodoc.analyzers.definitionfinder import (
    AssignData,
    ClassDefData,
    FunctionDefData,
    ImportFromData,
)
from nb_autodoc.annotation import Annotation
from nb_autodoc.config import Config, default_config
from nb_autodoc.log import logger
from nb_autodoc.modulefinder import ModuleFinder, ModuleProperties
from nb_autodoc.typing import (
    T_Annot,
    T_Autodoc,
    T_ClassMember,
    T_Definition,
    T_ModuleMember,
    isgenericalias,
)
from nb_autodoc.utils import (
    cached_property,
    cleandoc,
    find_name_in_mro,
    ismetaclass,
    isnamedtuple,
)

T = TypeVar("T")
TT = TypeVar("TT")


current_module: ContextVar["Module"] = ContextVar("current_module")
# NOTE: isfunction not recognize the C extension function (builtin), maybe isroutine and callable


_NULL: Any = object()


class AutodocRefineResult(NamedTuple):
    module: str
    attr: str
    is_ref: bool
    is_library: bool


def _refine_autodoc_from_ast(module: "Module", name: str) -> AutodocRefineResult | None:
    """Return source module where has name definition."""
    # should be circular guarded?
    chain = []
    attrs = []
    while True:
        analyzer = module.pyi_analyzer or module.py_analyzer
        # maybe reexport c extension? but it always appear in stub file
        assert analyzer, "found '__autodoc__' on non-source file"
        ast_obj = analyzer.scope.get(name)
        if ast_obj is None:
            return None
        if isinstance(ast_obj, ImportFromData):
            # found reference or library
            modules = module.manager.modules
            if ast_obj.module in modules:
                chain.append(module.name)
                attrs.append(name)
                module = modules[ast_obj.module]
                name = ast_obj.orig_name  # original name
            else:
                # if chain:  # ref should not be library
                #     return AutodocRefineResult(module.name, name, True, True)
                return AutodocRefineResult(module.name, name, False, True)
        else:
            # found definition
            if chain:
                return AutodocRefineResult(module.name, name, True, False)
            return AutodocRefineResult(module.name, name, False, False)


class ModuleManager:
    """Analyze all modules and store the context.

    To control module's documentable object, setting `__autodoc__` respects to:
        * module-level dict variable
        * key is the target object's qualified name in current module
        * value bool: True for whitelist, False for blacklist
        * value str: override target object's docstring

    Args:
        module: module or package
    """

    def __init__(
        self,
        module: str | ModuleType,
        *,
        config: Config | None = None,
    ) -> None:
        self.context: ChainMap[str, T_Definition] = ChainMap()
        """Context all members. Key is `module:qualname`."""
        self.config: Config = default_config.copy()
        if config is not None:
            self.config.update(config)
        self.name = module if isinstance(module, str) else module.__name__
        module_found_result = ModuleFinder(self.config).find_all_modules_wrapped(module)
        modules = {
            name: Module(self, name, py=m, pyi=ms)
            for name, m, ms in module_found_result.gen_bound_module()
        }
        self.modules: dict[str, Module] = modules
        self.prepare_module_members()

    def refine_autodoc(self, modules: dict[str, "Module"]) -> None:
        # clear manager context
        self.whitelist.clear()
        self.blacklist.clear()
        for module in modules.values():
            # clear module context
            module.exist_external.clear()
            autodoc = module.py__autodoc__
            for key, value in autodoc.items():
                name, _, attr = key.partition(".")
                result = _refine_autodoc_from_ast(module, name)
                if result is None:
                    logger.error(f"__autodoc__[{key!r}] not found")
                    continue
                if result.is_ref:
                    module.exist_external[name] = Reference(result.module, result.attr)
                elif result.is_library:
                    if result.module != module.name:
                        logger.error(
                            f"__autodoc__[{key!r}] is external import "
                            "but ends as library attribute"
                        )
                        continue
                    if attr:
                        logger.error(
                            f"__autodoc__[{key!r}] is library attribute "
                            f"with ambitious attr {attr!r}"
                        )
                        continue
                    if not isinstance(value, str):
                        logger.error(
                            f"__autodoc__[{key!r}] is library attribute "
                            f"and expects string value to override, got {type(value)}"
                        )
                        continue
                    module.exist_external[name] = LibraryAttr(module.name, name, value)
                refname = f"{result.module}:{result.attr}"
                if attr:  # no check attr existence
                    refname += "." + attr
                if value is True or isinstance(value, str):
                    self.whitelist.add(refname)
                elif value is False:
                    self.blacklist.add(refname)
                else:
                    logger.error(f"__autodoc__[{key!r}] got unexpected value {value}")

    def prepare_module_members(self) -> None:
        """Call `module.prepare` to filter internal reference."""
        for m in self.modules.values():
            m.prepare()

    def push_context(
        self, d: dict[str, T_Definition] | None = None
    ) -> dict[str, T_Definition]:
        """Push context. Like inplace `ChainMap.new_child`."""
        if d is None:
            d = {}
        self.context.maps.insert(1, d)
        return d

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name!r}>"


# external has two type "WeakReference" and "LibraryAttr"
class WeakReference:
    """External reference."""

    __slots__ = ("module", "attr")

    def __init__(self, module: str, attr: str) -> None:
        self.module = module
        self.attr = attr

    def find_definition(
        self, context: Mapping[str, T_Definition]
    ) -> T_Definition | None:
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(module={self.module!r}, attr={self.attr!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WeakReference):
            return False
        return self.module == other.module and self.attr == other.attr


class LibraryAttr:
    """External library attribute."""

    __slots__ = ("module", "name", "doc")

    def __init__(self, module: str, name: str, docstring: str) -> None:
        self.module = module  # the user module, not library
        self.name = name
        self.doc = cleandoc(docstring)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, docstring={self.doc!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LibraryAttr):
            return False
        return self.name == other.name and self.doc == other.doc


class Module:
    """Analyze module."""

    def __init__(
        self,
        manager: "ModuleManager",
        name: str,
        *,
        py: ModuleProperties | None = None,
        pyi: ModuleProperties | None = None,
    ) -> None:
        self.manager = manager
        self.context = manager.push_context()
        self.members: dict[str, T_ModuleMember] = {}
        self.name = name
        # if py and pyi both exist, then py (include extension) is only used to extract docstring
        # if one of them exists, then analyze that one
        # if py is not sourcefile, pyi must be specified (find definition), otherwise skip
        # such as numpy._typing._ufunc or torch._C._autograd
        if py is None and pyi is None:
            raise RuntimeError
        self.py = py
        self.pyi = pyi
        docstring = None
        if pyi and pyi.sm_doc:
            docstring = pyi.sm_doc
        elif py and py.sm_doc:
            docstring = py.sm_doc
        self.doc = docstring and cleandoc(docstring)
        py_analyzer = pyi_analyzer = None
        if py and py.is_source:
            py_analyzer = Analyzer(self.name, self.package, cast(str, py.sm_file))
            py_analyzer.analyze()
        if pyi:  # pyi always sourcefile
            pyi_analyzer = Analyzer(self.name, self.package, cast(str, pyi.sm_file))
            pyi_analyzer.analyze()
        self.py_analyzer = py_analyzer
        self.pyi_analyzer = pyi_analyzer
        self.whitelist: set[str] = set()
        """Module member whitelist."""
        self.blacklist: set[str] = set()
        """Module member blacklist."""
        # dotted whitelist/blacklist consumed by class, the remaining item must be reference
        self.dotted_whitelist: dict[str, set[str]] = defaultdict(set)
        self.dotted_blacklist: dict[str, set[str]] = defaultdict(set)
        for name, val in self.py__autodoc__.items():
            if "." in name:
                name, _, attrs = name.partition(".")
                if val:
                    self.dotted_whitelist[name].add(attrs)
                else:
                    self.dotted_blacklist[name].add(attrs)
            else:
                if val:
                    self.whitelist.add(name)
                else:
                    self.blacklist.add(name)

    @property
    def is_bare_c_extension(self) -> bool:
        if self.pyi is None and self.py is not None:
            return self.py.is_c_module
        return False

    @property
    def has_source(self) -> bool:
        return self.pyi is not None or (self.py is not None and self.py.is_source)

    @property
    def package(self) -> str | None:
        if self.py:
            return self.py.sm_package
        if self.pyi:
            return self.pyi.sm_package
        raise RuntimeError

    @property
    def annotations(self) -> dict[str, T_Annot]:
        return self.prime_module_dict.get("__annotations__", {})

    @property
    def prime_analyzer(self) -> Analyzer:
        prime = self.pyi_analyzer or self.py_analyzer
        if prime is not None:
            return prime
        raise RuntimeError

    @property
    def prime_module_dict(self) -> dict[str, Any]:
        """Return runtime module dict."""
        prime = self.pyi or self.py
        if prime is not None:
            return prime.sm_dict
        raise RuntimeError

    @property
    def py__autodoc__(self) -> T_Autodoc:
        """Retrieve `__autodoc__` bound on current module."""
        res = {}
        if self.py:
            res.update(self.py.sm_dict.get("__autodoc__", ()))
        if self.pyi:
            res.update(self.pyi.sm_dict.get("__autodoc__", ()))
        assert all(
            all(name.isidentifier() for name in qualname.split(".")) for qualname in res
        ), f"bad '__autodoc__': {res}"
        return res

    @cached_property
    def t_namespace(self) -> dict[str, Any]:
        """Return type checking namespace.

        Stub-only imports are replaced by `Type[TypeCheckingClass]`.
        """
        globals_ = self.prime_module_dict.copy()
        self.prime_analyzer.exec_type_checking_body(
            self.prime_analyzer.module.type_checking_body, globals_
        )
        return globals_

    # def attrgetter(self, name: str)

    def add_member(self, name: str, obj: T_ModuleMember) -> None:
        self.members[name] = self.context[f"{self.name}:{name}"] = obj

    def prepare(self) -> None:
        """Build module members."""
        self.members.clear()
        if not self.has_source:
            return
        ast_scope = self.prime_analyzer.module.scope
        libdocs = {k: v for k, v in self.py__autodoc__.items() if isinstance(v, str)}
        for name, astobj in ast_scope.items():
            pyobj = self.t_namespace.get(name, _NULL)
            if pyobj is _NULL:
                # TODO: _NULL and pyi, then get from py dict
                # explicitly deleted by `del name`. just pass
                logger.warning(f"ignore {self.name}:{name}")
                continue
            if isinstance(astobj, ImportFromData):
                if name in libdocs:
                    self.add_member(
                        name, LibraryAttr(self.name, name, libdocs.pop(name))
                    )
                # lazy reference. resolve on whitelisting
                elif astobj.module in self.manager.modules:
                    self.add_member(
                        name, WeakReference(astobj.module, astobj.orig_name)
                    )
            elif isinstance(astobj, ClassDefData):
                # pass if class is decorated as function or other types
                if not isinstance(pyobj, type):
                    continue
                self.add_member(name, Class(name, pyobj, astobj, module=self))
            elif isinstance(pyobj, (FunctionType, BuiltinFunctionType)):
                if isinstance(pyobj, BuiltinFunctionType):
                    # is import user c extension function and redefine by assignment
                    # if not isextbuiltin(pyobj, self.manager.name):
                    #     continue
                    # TODO: add c extension support
                    # support for c extension function or reexport class (ambitious member)
                    # we needs another config for this
                    continue
                if pyobj.__name__ == "<lambda>":
                    self.add_member(name, Variable(name, pyobj, astobj, module=self))
                    continue
                assign_doc = None
                if isinstance(astobj, AssignData) and astobj.docstring:
                    assign_doc = cleandoc(astobj.docstring)
                self.add_member(
                    name,
                    Function(
                        name,
                        pyobj,
                        astobj if isinstance(astobj, FunctionDefData) else None,
                        module=self,
                        assign_doc=assign_doc,
                    ),
                )
            elif isinstance(astobj, AssignData):
                # maybe dynamic class creation or class type alias
                self.add_member(name, Variable(name, pyobj, astobj, module=self))
            else:
                logger.warning(f"skip analyze {name!r} in module {self.name!r}")
        if libdocs:
            logger.warning(f"cannot solve autodoc item {libdocs}")

    def _evaluate(self, s: str, *, locals: dict[str, Any] | None = None) -> Any:
        # some library has stmt like `if TYPE_CHECKING...else...`
        # so we need to create type_checking namespace rather than ChainMap
        # for class method, give class namespace as `locals`
        return eval(s, cast("dict[str, Any]", self.prime_module_dict), locals)

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} {self.name!r} "
            f"py from {self.py and self.py.sm_file!r} "
            f"pyi from {self.pyi and self.pyi.sm_file!r}>"
        )


class Class:
    """Analyze class."""

    # whitelist members in filter
    SPECIAL_MEMBERS = ["__get__", "__set__", "__delete__"]

    def __init__(
        self, name: str, pyobj: type, astobj: ClassDefData, *, module: Module
    ) -> None:
        self.name = name
        docstring = pyobj.__doc__  # TODO: add inherit config
        self.doc = docstring and cleandoc(docstring)
        self.pyobj = pyobj
        self.astobj = astobj
        self.module = module
        self.members: dict[str, T_ClassMember] = {}
        self.instvars: dict[str, Variable] = {}
        self.prepare()

    @property
    def objtype(self) -> Literal["class", "metaclass", "namedtuple", "enum"]:
        # objtype maybe relate to object indicator
        obj = self.pyobj
        if isnamedtuple(obj):
            return "namedtuple"
        elif issubclass(obj, Enum):
            return "enum"
        if ismetaclass(obj):
            return "metaclass"
        return "class"

    @property
    def kind(self) -> str:
        # kind is documentation prefix
        ...

    @property
    def qualname(self) -> str:
        return self.name  # nested class not support

    @property
    def fullname(self) -> str:
        return f"{self.module.name}:{self.qualname}"

    @cached_property
    def t_namespace(self) -> dict[str, Any]:
        globals_ = self.module.t_namespace
        locals_ = self.pyobj.__dict__.copy()
        self.module.prime_analyzer.exec_type_checking_body(
            self.astobj.type_checking_body, globals_, locals_
        )
        return locals_

    def add_member(self, name: str, obj: T_ClassMember) -> None:
        self.members[name] = obj
        self.module.context[f"{self.fullname}.{name}"] = obj

    def prepare(self) -> None:
        """Build class members."""
        self.members.clear()
        clsobj = self.pyobj
        annotations = self.t_namespace.get("__annotations__", {})
        ast_scope = self.astobj.scope
        ast_instance_vars = self.astobj.instance_vars
        if issubclass(clsobj, Enum):
            for name, member in clsobj.__members__.items():
                doc = None
                astobj = ast_scope[name]
                if isinstance(astobj, AssignData) and astobj.docstring:
                    doc = cleandoc(astobj.docstring)
                self.add_member(name, EnumMember(name, member.value, doc))
            return
        instvar_names = []  # type: list[str]
        # slots = clsobj_dict.get("__slots__", None)
        # NOTE: now we don't care the `__slots__` on class
        if isnamedtuple(clsobj):
            instvar_names.extend(clsobj._fields)
        else:
            for name in annotations.keys():
                if find_name_in_mro(clsobj, name, _NULL) is _NULL:
                    instvar_names.append(name)
            instvar_names.extend(ast_instance_vars.keys())
        # prepare instance vars
        for name in dict.fromkeys(instvar_names).keys():
            cls_inst = ast_scope.get(name)
            init_inst = ast_instance_vars.get(name)
            if cls_inst and not isinstance(cls_inst, AssignData):
                raise RuntimeError(f"instance var {name!r} must be Assign")
            if cls_inst:
                astobj = cast(AssignData, cls_inst)  # cast for mypy
                if init_inst:
                    astobj.merge(init_inst)
            elif init_inst:
                astobj = init_inst
            else:
                logger.warning(f"ignore instance var {self.fullname}.{name}")
                continue
            self.instvars[name] = Variable(
                name, _NULL, astobj, module=self.module, cls=self, instvar=True
            )
        # prepare class members
        for name, astobj in ast_scope.items():
            if name in self.instvars:
                # maybe also class-var definition but we ignore
                continue
            dict_obj = self.t_namespace.get(name, _NULL)
            if dict_obj is _NULL:
                # annotation only or deleted or superclass
                logger.warning(f"ignore {self.fullname}.{name}")
                continue
            is_lambda = (
                isinstance(dict_obj, FunctionType) and dict_obj.__name__ == "<lambda>"
            )
            if isinstance(astobj, (ImportFromData, ClassDefData)):
                pass
            elif (
                isinstance(dict_obj, (staticmethod, classmethod, FunctionType))
                and not is_lambda
            ):
                assign_doc = None
                if isinstance(astobj, AssignData) and astobj.docstring:
                    assign_doc = cleandoc(astobj.docstring)
                self.add_member(
                    name,
                    Function(
                        name,
                        dict_obj,
                        astobj if isinstance(astobj, FunctionDefData) else None,
                        module=self.module,
                        cls=self,
                        assign_doc=assign_doc,
                    ),
                )
            elif isinstance(dict_obj, property):
                if not isinstance(astobj, (FunctionDefData, AssignData)):
                    continue
                self.add_member(
                    name,
                    Variable(name, dict_obj, astobj, module=self.module, cls=self),
                )
            elif isinstance(astobj, AssignData) or is_lambda:
                self.add_member(
                    name, Variable(name, dict_obj, astobj, module=self.module, cls=self)
                )
            else:
                logger.warning(f"skip analyze {name!r} in class {self.name!r}")

    def __repr__(self) -> str:
        doc = self.doc and self.doc[:8] + "..."
        return f"<{self.__class__.__name__} {self.name!r} doc={doc!r}>"


class EnumMember(NamedTuple):
    name: str
    value: Any
    doc: str | None


# TODO: add MethodType support on module-level, those are alias of bound method
class Function:
    """Analyze function.

    **Overloads:**

    In py3.11+, `typing.get_overloads` is implemented based on overload registry dict
    like `{module: {qualname: {firstlineno: func}}}`, so stub evaluation will cover
    the potential overloads. We do not take care of this implementation.
    """

    def __init__(
        self,
        name: str,
        pyobj: FunctionType | staticmethod[Any] | classmethod[Any],
        astobj: FunctionDefData | None,
        *,
        module: Module,
        cls: Class | None = None,
        assign_doc: str | None = None,
    ) -> None:
        self.name = name
        if isinstance(pyobj, FunctionType):
            func = pyobj
        elif not isinstance(pyobj.__func__, FunctionType):
            raise RuntimeError("staticmethod or classmethod must be FunctionType")
        else:
            func = pyobj.__func__
        self.pyobj = pyobj
        self.func = func
        doc = assign_doc
        if not doc:
            doc = pyobj.__doc__ and cleandoc(pyobj.__doc__)
        self.doc = doc
        # None if function is dynamic creation without overload or c extension reexport
        self.astobj = astobj
        self.module = module
        self.cls = cls
        # evaluate signature_from_ast `expr | str` using globals and class locals
        # __text_signature__ should be respected
        # https://github.com/python/cpython/blob/5cf317ade1e1b26ee02621ed84d29a73181631dc/Objects/typeobject.c#L8597
        # catch signature ValueError if is BuiltinFunctionType

    @property
    def qualname(self) -> str:
        if self.cls:
            return f"{self.cls.qualname}.{self.name}"
        return self.name

    @property
    def fullname(self) -> str:
        return f"{self.module.name}:{self.qualname}"

    def __repr__(self) -> str:
        lineno = self.func.__code__.co_firstlineno
        return f"<{self.__class__.__name__} {self.qualname!r} lineno={lineno}>"


class Variable:
    """Analyze variable."""

    def __init__(
        self,
        name: str,
        pyobj: Any | object | property,
        astobj: AssignData | FunctionDefData,
        *,
        module: Module,
        cls: Class | None = None,
        instvar: bool = False,
    ) -> None:
        # only ast_function in property
        # assert not (isinstance(astobj, FunctionDefData) and not isinstance(pyobj, property))
        self.name = name
        self.pyobj = pyobj
        self.astobj = astobj
        self.module = module
        self.cls = cls
        self.instvar = instvar

    @property
    def qualname(self) -> str:
        if self.cls is None:
            return self.name
        return f"{self.cls.qualname}.{self.name}"

    @property
    def fullname(self) -> str:
        return f"{self.module.name}:{self.qualname}"

    @property
    def is_typealias(self) -> bool:
        annotation = self.get_annotation()
        if isgenericalias(self.pyobj) or (annotation and annotation.is_typealias):
            return True
        return False

    def get_annotation(self) -> Annotation | None:
        ann = self.astobj.annotation if isinstance(self.astobj, AssignData) else None
        if not ann:
            return None
        return Annotation(
            ann,
            _AnnContext(
                self.module.prime_analyzer.module.typing_module,
                self.module.prime_analyzer.module.typing_names,
            ),
        )

    @cached_property
    def annotation_(self) -> str:
        annot = self.annot
        if annot is NULL:
            return "untyped"
        elif isinstance(annot, str):
            if "->" in annot:
                logger.warning(
                    f"{self.module.name} | disallow alternative Callable syntax "
                    f"in {self.qualname} {annot!r}"
                )
                return self.replace_annot_refs(annot)
            # TODO: add "X | Y" parser feature
            try:
                annot = self.module._evaluate(annot)
            except Exception as e:  # TypeError if "X | Y"
                logger.error(
                    f"{self.module.name} | error evaluating annotation {self.qualname} {e}"
                )
            else:
                annot = formatannotation(annot, {})
        elif isinstance(annot, Tp_GenericAlias):
            annot = eval_annot_as_possible(
                annot,
                self.module.obj.__dict__,
                f"failed evaluating annotation {self.refname}",
            )
            annot = formatannotation(annot, {})
        else:  # type or None
            annot = formatannotation(annot, {})
        return convert_annot(self.replace_annot_refs(annot))

    def replace_annot_refs(self, s: str) -> str:
        return s

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.qualname!r} instvar={self.instvar}>"


class _AnnContext(NamedTuple):
    typing_module: list[str]
    typing_names: dict[str, str]
