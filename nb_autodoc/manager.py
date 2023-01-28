"""Inspect and analyze module from runtime and AST."""

from __future__ import annotations as _

import ast
import dataclasses
from inspect import Parameter, Signature, getsource, unwrap
from types import FunctionType, MappingProxyType, ModuleType
from typing import Any, Dict, NamedTuple, TypeVar, cast

from nb_autodoc.analyzers.analyzer import Analyzer
from nb_autodoc.analyzers.definitionfinder import (
    AssignData,
    ClassDefData,
    FunctionDefData,
    ImportFromData,
)
from nb_autodoc.analyzers.utils import signature_from_ast
from nb_autodoc.annotation import Annotation
from nb_autodoc.config import Config, default_config
from nb_autodoc.docstringparser import GoogleStyleParser
from nb_autodoc.log import current_module, logger
from nb_autodoc.modulefinder import ModuleFinder, ModuleProperties
from nb_autodoc.nodes import Docstring
from nb_autodoc.typing import (
    T_ClassMember,
    T_Definition,
    T_DefinitionOrRef,
    T_ModuleMember,
    isgenericalias,
)
from nb_autodoc.utils import (
    cached_property,
    cleandoc,
    dedent,
    isenumclass,
    isnamedtuple,
)

T = TypeVar("T")
TT = TypeVar("TT")
_TS = TypeVar("_TS", bound=Signature)


def parse_doc(s: str, config: Config) -> Docstring:
    docformat = config["docstring_format"]
    if docformat == "google":
        dsobj = GoogleStyleParser(s, config["docstring_indent"])
        return dsobj.parse()
    else:
        raise ValueError(f"unknown docstring format {docformat!r}")


def _unwrap_until_sig(obj: Any) -> Any:
    obj = unwrap(obj, stop=(lambda f: hasattr(f, "__signature__")))
    return obj


def get_signable_func(obj: Any) -> Any:
    """Get unwrapped function and signable function for class."""
    if not callable(obj):
        raise ValueError(f"{obj!r} is not callable")
    if isinstance(obj, type):
        if type(obj).__call__ is not type.__call__:
            return _unwrap_until_sig(obj.__call__)
        elif obj.__new__ is not object.__new__:
            return _unwrap_until_sig(obj.__new__)
        elif getattr(obj, "__init__") is not object.__init__:
            return _unwrap_until_sig(getattr(obj, "__init__"))
        # nothing to signature
        return getattr(object, "__init__")
    else:
        return _unwrap_until_sig(obj)


class AnnParameter(Parameter):
    annotation: Annotation | Any  # annotation or _empty


class FunctionSignature(Signature):
    """Precious signature for FunctionType."""

    parameters: MappingProxyType[str, AnnParameter]
    return_annotation: Annotation | Any


class Context(Dict[str, T_DefinitionOrRef]):
    """Context all members. Dictionary key is `module:qualname`."""

    def link_class_by_mro(self) -> None:
        """Find class resolution order."""
        classes = {i.pyobj: i for i in self.values() if isinstance(i, Class)}
        for clsobj in classes:
            classes[clsobj].mro = tuple(
                classes[i] for i in clsobj.__mro__[1:-1] if i in classes
            )


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
        self.context: Context = Context()
        self.config: Config = default_config.copy()
        if config is not None:
            self.config.update(config)
        self.name = module if isinstance(module, str) else module.__name__
        module_found_result = ModuleFinder(self.config).find_all_modules_wrapped(module)
        modules = {
            name: Module(self, name, py=m, pyi=ms)
            for name, m, ms in module_found_result.gen_bound_module()
        }
        self.prepared = False
        self.modules: dict[str, Module] = modules
        for m in self.modules.values():
            m.prepare()
        self.prepared = True
        # the context is loaded, now build the mro of class
        self.context.link_class_by_mro()

    @property
    def is_single_module(self) -> bool:
        return len(self.modules) == 1 and not self.modules[self.name].is_package

    def parse_doc(self, s: str) -> Docstring:
        return parse_doc(s, self.config)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name!r}>"


class ImportRef:
    """Import reference."""

    __slots__ = ("name", "module", "ref")

    def __init__(self, name: str, module: "Module", ref: str) -> None:
        self.name = name
        self.module = module
        self.ref = ref

    def find_definition(self) -> T_ModuleMember | None:
        ref = self.ref
        context = self.module.manager.context
        for _ in range(100):  # or parameter guard
            if ref not in context:
                break
            dobj = context[ref]
            if not isinstance(dobj, ImportRef):
                return cast(T_ModuleMember, dobj)
            ref = dobj.ref
        else:
            # two import from point to each other?
            raise RuntimeError("reference max iter exceeded")

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name={self.name!r}, "
            f"module={self.module!r}, ref={self.ref!r})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ImportRef):
            return False
        return (
            self.name == other.name
            and self.module == other.module
            and self.ref == other.ref
        )


class Module:
    """Analyze module."""

    def __init__(
        self,
        manager: ModuleManager,
        name: str,
        *,
        py: ModuleProperties | None = None,
        pyi: ModuleProperties | None = None,
    ) -> None:
        self.manager = manager
        self.members: dict[str, T_ModuleMember | ImportRef] = {}
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
        self.doctree = manager.parse_doc(self.doc) if self.doc is not None else None
        py_analyzer = pyi_analyzer = None
        if py and py.is_source:
            py_analyzer = Analyzer(self.name, self.package, cast(str, py.sm_file))
            py_analyzer.analyze()
        if pyi:  # pyi always sourcefile
            pyi_analyzer = Analyzer(self.name, self.package, cast(str, pyi.sm_file))
            pyi_analyzer.analyze()
        self.py_analyzer = py_analyzer
        self.pyi_analyzer = pyi_analyzer

    @property
    def is_bare_c_extension(self) -> bool:
        if self.pyi is None and self.py is not None:
            return self.py.is_c_module
        return False

    @property
    def is_package(self) -> bool:
        return self.prime_py.is_package

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
    def prime_analyzer(self) -> Analyzer:
        prime = self.pyi_analyzer or self.py_analyzer
        if prime is not None:
            return prime
        raise RuntimeError

    @property
    def prime_py(self) -> ModuleProperties:
        prime = self.pyi or self.py
        if prime is not None:
            return prime
        raise RuntimeError

    @property
    def prime_module_dict(self) -> dict[str, Any]:
        """Return runtime module dict."""
        return self.prime_py.sm_dict

    @cached_property
    def py__autodoc__(self) -> dict[str, bool | str]:
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

        Stub imports are replaced by `Type[TypeCheckingClass]`.
        """
        globalns = self.prime_module_dict.copy()
        _copy__annotations__(globalns)
        self.prime_analyzer._exec_stub_safe(
            self.prime_analyzer.module.type_checking_body, globalns
        )
        return globalns

    def add_member(self, name: str, obj: T_ModuleMember | ImportRef) -> None:
        self.members[name] = self.manager.context[f"{self.name}:{name}"] = obj

    def get_canonical_member(self, qualname: str) -> T_Definition | None:
        """Find canonical member definition.

        Resolve import reference and class mro member.
        """
        clsname, dot, attr = qualname.partition(".")
        dobj = self.members.get(clsname)  # type: T_DefinitionOrRef | None
        if dobj is not None:
            if isinstance(dobj, ImportRef):
                dobj = dobj.find_definition()
            if not dot:
                return dobj
            if not isinstance(dobj, Class):
                return None
            return dobj.get_canonical_member(attr)

    def get_all_definitions(self) -> Dict[str, T_Definition]:
        defs: dict[str, T_Definition] = {}
        for member in self.members.values():
            if isinstance(member, ImportRef):
                ref_found = member.find_definition()
                if ref_found:
                    defs[ref_found.qualname] = ref_found
            elif isinstance(member, Class):
                for clsmember in member.members.values():
                    defs[clsmember.qualname] = clsmember
            else:
                defs[member.qualname] = member
        return defs

    def prepare(self) -> None:
        """Build module members."""
        self.members.clear()
        if not self.has_source:
            return
        ast_scope = self.prime_analyzer.module.scope
        libdocs = {k: v for k, v in self.py__autodoc__.items() if isinstance(v, str)}
        _NULL = object()
        for name, astobj in ast_scope.items():
            pyobj = self.t_namespace.get(name, _NULL)
            if pyobj is _NULL:
                # explicitly deleted by `del name`. just pass
                logger.warning(f"ignored {self.name}:{name}")
                continue
            is_lambda = isinstance(pyobj, FunctionType) and pyobj.__name__ == "<lambda>"
            if isinstance(astobj, ImportFromData):
                if name in libdocs:
                    self.add_member(name, LibraryAttr(self, name, libdocs.pop(name)))
                # lazy reference. resolve on whitelisting
                elif astobj.module in self.manager.modules:
                    self.add_member(
                        name,
                        ImportRef(name, self, f"{astobj.module}:{astobj.orig_name}"),
                    )
            elif isinstance(astobj, ClassDefData):
                # pass if ClassDef is decorated as function or other types
                if not isinstance(pyobj, type):
                    continue
                self.add_member(name, Class(name, pyobj, astobj, module=self))
            elif isinstance(pyobj, FunctionType) and not is_lambda:
                # is import user c extension function and redefine by assignment
                # if not isextbuiltin(pyobj, self.manager.name):
                #     continue
                # TODO: add c extension support
                # support for c extension function or reexport class (ambitious member)
                # we needs another config for this
                astobj_val = astobj if isinstance(astobj, FunctionDefData) else None
                assign_doc = None
                if isinstance(astobj, AssignData) and astobj.docstring:
                    assign_doc = cleandoc(astobj.docstring)
                self.add_member(
                    name,
                    Function(
                        name, pyobj, astobj_val, module=self, assign_doc=assign_doc
                    ),
                )
            else:
                # maybe dynamic class creation or class type alias or lambda
                self.add_member(name, Variable(name, pyobj, astobj, module=self))
        if libdocs:
            logger.warning(f"cannot solve autodoc item {libdocs}")

    def build_static_ann(self, expr: ast.expr) -> Annotation:
        return Annotation(
            expr,
            _AnnContext(
                self.prime_analyzer.module.typing_module,
                self.prime_analyzer.module.typing_names,
            ),
            globalns=self.get_all_definitions(),
        )

    def get_signature(self, func: FunctionType) -> FunctionSignature:
        """Get signature from concrete FunctionType."""
        if not func.__module__ == self.name:
            raise RuntimeError(
                f"function {func.__name__!r} is defined on {func.__module__!r}"
            )
        source = dedent(getsource(func))
        node = ast.parse(source).body[0]
        assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        _empty = Parameter.empty
        sig = signature_from_ast(node.args, node.returns)
        params = sig.parameters.copy()
        for param in sig.parameters.values():
            annotation = param.annotation
            default = param.default
            if annotation is not _empty:
                annotation = self.build_static_ann(annotation)
            if default is not _empty:
                default = _AlwaysStr(ast.get_source_segment(source, default))
            params[param.name] = param.replace(annotation=annotation, default=default)
        return_annotation = sig.return_annotation
        if return_annotation is not _empty:
            return_annotation = self.build_static_ann(return_annotation)
        return FunctionSignature(
            list(params.values()), return_annotation=return_annotation
        )

    # def _evaluate(self, s: str, *, locals: dict[str, Any] | None = None) -> Any:
    #     # some library has stmt like `if TYPE_CHECKING...else...`
    #     # so we need to create type_checking namespace rather than ChainMap
    #     # for class method, give class namespace as `locals`
    #     return eval(s, self.prime_module_dict, locals)

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} {self.name!r} "
            f"py from {self.py and self.py.sm_file!r} "
            f"pyi from {self.pyi and self.pyi.sm_file!r}>"
        )


# LibraryAttr only appears in module
class LibraryAttr:
    """External library attribute."""

    __slots__ = ("module", "name", "doc", "doctree")

    def __init__(self, module: Module, name: str, docstring: str) -> None:
        self.module = module  # the user module, not library
        self.name = name
        self.doc = cleandoc(docstring)
        self.doctree = module.manager.parse_doc(self.doc)

    @property
    def qualname(self) -> str:
        return self.name

    @property
    def fullname(self) -> str:
        return f"{self.module.name}:{self.name}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, doc={self.doc!r})"


# Class only appears in module
class Class:
    """Analyze class."""

    mro: tuple[Class, ...]

    _ANNONLY_MEMBER: Any = object()
    """Annotation only member placeholder."""

    def __init__(
        self, name: str, pyobj: type, astobj: ClassDefData, *, module: Module
    ) -> None:
        self.name = name
        docstring = pyobj.__doc__  # TODO: add inherit config
        self.doc = docstring and cleandoc(docstring)
        self.doctree = (
            module.manager.parse_doc(self.doc) if self.doc is not None else None
        )
        self.pyobj = pyobj
        self.astobj = astobj
        self.module = module
        self.members: dict[str, T_ClassMember] = {}
        self.prepare()

    @property
    def qualname(self) -> str:
        return self.name  # nested class not support

    @property
    def fullname(self) -> str:
        return f"{self.module.name}:{self.qualname}"

    @cached_property
    def t_namespace(self) -> dict[str, Any]:
        globalns = self.module.t_namespace
        localns = self.pyobj.__dict__.copy()
        _copy__annotations__(localns)
        self.module.prime_analyzer._exec_stub_safe(
            self.astobj.type_checking_body, globalns, localns
        )
        return localns

    @cached_property
    def signature(self) -> FunctionSignature | None:
        """Get signature on class, or None."""
        if not self.module.manager.prepared:
            raise RuntimeError
        sig = Function._get_signature(self.pyobj, self.module.manager.modules)
        if sig:
            return _skip_signature_bound_arg(sig)

    def add_member(self, name: str, obj: T_ClassMember) -> None:
        self.members[name] = self.module.manager.context[
            f"{self.fullname}.{name}"
        ] = obj

    def get_canonical_member(self, name: str) -> T_ClassMember | None:
        # if "mro" not in self.__dict__:
        #     raise RuntimeError("module has not been prepared")
        dobj = self.members.get(name)
        if dobj is not None:
            return dobj
        for base in self.mro:
            if name in base.members:
                return base.members[name]

    def prepare(self) -> None:
        """Build class members."""
        self.members.clear()
        clsobj = self.pyobj
        # annotations = self.t_namespace.get("__annotations__", {})
        ast_scope = self.astobj.scope
        ast_instance_vars = self.astobj.instance_vars
        # _NULL = object()
        if isenumclass(clsobj):
            for name, member in clsobj.__members__.items():
                doc = None
                astobj = ast_scope[name]
                if isinstance(astobj, AssignData) and astobj.docstring:
                    doc = cleandoc(astobj.docstring)
                self.add_member(
                    name,
                    EnumMember(name, member.value, doc, cls=self, module=self.module),
                )
            return
        instvar_names = []  # type: list[str]
        # slots = clsobj_dict.get("__slots__", None)
        # NOTE: now we don't care the `__slots__` on class
        if isnamedtuple(clsobj):
            instvar_names.extend(clsobj._fields)
        else:
            for name, astobj in ast_scope.items():
                if isinstance(astobj, AssignData) and astobj.value is None:
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
                    astobj = astobj.merge(init_inst)
            elif init_inst:
                astobj = init_inst
            else:
                logger.error(f"ignored instance var {self.fullname}.{name}")
                continue
            # ClassVar[...] is checked by Variable constructor
            self.add_member(
                name,
                Variable(
                    name,
                    Class._ANNONLY_MEMBER,
                    astobj,
                    module=self.module,
                    cls=self,
                    is_instvar=True,
                ),
            )
        # prepare class members
        for name, astobj in ast_scope.items():
            if name in self.members:
                # already instance var. maybe also classvar but ignore
                continue
            # member maybe superclass or Mixin that undocumented
            # but we should have another config for that case
            # class member constructor always focus on its dict members
            dict_obj = self.t_namespace.get(name, Class._ANNONLY_MEMBER)
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
            else:
                self.add_member(
                    name, Variable(name, dict_obj, astobj, module=self.module, cls=self)
                )
            # else:
            #     logger.warning(f"skip analyze {name!r} in class {self.name!r}")

    def __repr__(self) -> str:
        doc = _truncate_doc(self.doc)
        return f"<{self.__class__.__name__} {self.name!r} doc={doc!r}>"


# Function appears in module and class
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
            doc = func.__doc__ and cleandoc(func.__doc__)
        self.doc = doc
        self.doctree = (
            module.manager.parse_doc(self.doc) if self.doc is not None else None
        )
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

    @cached_property
    def signature(self) -> FunctionSignature | None:
        """Get signature on unwrapped function, or None."""
        if not self.module.manager.prepared:
            raise RuntimeError
        sig = Function._get_signature(self.func, self.module.manager.modules)
        if sig and self.cls and isinstance(self.pyobj, (FunctionType, classmethod)):
            return _skip_signature_bound_arg(sig)
        return sig

    @staticmethod
    def _get_signature(
        obj: Any, modules: dict[str, Module]
    ) -> FunctionSignature | None:
        func = get_signable_func(obj)
        if not isinstance(func, FunctionType):
            # maybe functionlike, such as cython function
            return None
        if not _validate_filename(func.__code__.co_filename):
            # function has no source code
            # maybe created by codegen (exec), such as dataclass
            return None
        modulename = func.__module__
        if modulename in modules:
            return modules[modulename].get_signature(func)
        else:
            logger.info(
                f"'{obj.__qualname__}.{func.__name__}' is defined on {func.__module__!r} "
                "which is unreachable"
            )

    def __repr__(self) -> str:
        lineno = self.func.__code__.co_firstlineno
        return f"<{self.__class__.__name__} {self.qualname!r} lineno={lineno}>"


# Variable appears in module and class
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
        is_instvar: bool = False,
    ) -> None:
        # only ast_function in property
        # assert not (isinstance(astobj, FunctionDefData) and not isinstance(pyobj, property))
        self.name = name
        self.pyobj = pyobj
        self.astobj = astobj
        self.module = module
        self.cls = cls
        docstring = None
        if isinstance(astobj, AssignData):
            docstring = astobj.docstring
        elif isinstance(pyobj, property):
            docstring = pyobj.__doc__
        self.doc = docstring and cleandoc(docstring)
        self.doctree = (
            module.manager.parse_doc(self.doc) if self.doc is not None else None
        )
        self._is_instvar = is_instvar

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
        annotation = self.annotation
        # don't make class to be type alias
        if isgenericalias(self.pyobj) or (annotation and annotation.is_typealias):
            return True
        return False

    @property
    def is_instvar(self) -> bool:
        if self._is_instvar is True:
            ann = self.annotation
            if ann and ann.is_classvar:
                return False
        return self._is_instvar

    @cached_property
    def annotation(self) -> Annotation | None:
        if not self.module.manager.prepared:
            raise RuntimeError
        if isinstance(self.astobj, AssignData):
            var_annotation = None
            if self.astobj.annotation:
                var_annotation = self.module.build_static_ann(self.astobj.annotation)
            # var annotation is TypeAlias, or assignment value is genericalias
            if (var_annotation and var_annotation.is_typealias) or (
                not var_annotation and isgenericalias(self.pyobj)
            ):
                assert self.astobj.value, "TypeAlias must have assignment value"
                var_annotation = self.module.build_static_ann(
                    ast.parse(self.astobj.value, mode="eval").body
                )
            return var_annotation
        elif isinstance(self.pyobj, property) and self.pyobj.fget:
            sig = Function._get_signature(self.pyobj.fget, self.module.manager.modules)
            if sig and sig.return_annotation is not Parameter.empty:
                return sig.return_annotation

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} {self.qualname!r} instvar={self.is_instvar}>"
        )


# TODO: replace these classes with dataclass and do procedure analysis
# EnumMember only appears in class
@dataclasses.dataclass(eq=False)
class EnumMember:
    """Enumeration class members.

    Enum member has different documentation from `Variable`.
    """

    name: str
    value: Any
    doc: str | None
    cls: Class
    module: Module

    def __post_init__(self) -> None:
        self.doctree = (
            self.module.manager.parse_doc(self.doc) if self.doc is not None else None
        )

    @property
    def qualname(self) -> str:
        return f"{self.cls.qualname}.{self.name}"

    @property
    def fullname(self) -> str:
        return f"{self.module.name}:{self.name}"


class _AnnContext(NamedTuple):
    typing_module: list[str]
    typing_names: dict[str, str]


class _AlwaysStr(str):
    # let str.__repr__ have no change
    def __repr__(self) -> str:
        return self.__str__()


def _skip_signature_bound_arg(sig: _TS) -> _TS:
    # skip first argument
    params = tuple(sig.parameters.values())
    if not params or params[0].kind in (
        Parameter.VAR_KEYWORD,
        Parameter.KEYWORD_ONLY,
    ):
        raise ValueError(f"invalid method signature {sig}")
    kind = params[0].kind
    if kind in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD):
        params = params[1:]
    else:
        # it is var-positional, do nothing
        pass
    return sig.replace(parameters=params)


def _copy__annotations__(_ns: dict[str, Any]) -> None:
    if "__annotations__" in _ns:
        _ns["__annotations__"] = _ns["__annotations__"].copy()


def _validate_filename(filename: str) -> bool:
    return not (filename.startswith("<") and filename.endswith(">"))


def _truncate_doc(doc: str | None) -> str | None:
    return doc and doc[:16].rstrip() + "..."
