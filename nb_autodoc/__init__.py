import inspect
import re
import sys
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    NamedTuple,
    Optional,
    Set,
    Type,
    TypeVar,
    Union,
)
from pathlib import Path
from types import ModuleType
from collections import UserDict
from importlib import import_module
from pkgutil import iter_modules
from textwrap import dedent

from nb_autodoc import schema, pycode, utils
from nb_autodoc.utils import formatannotation


T = TypeVar("T")
T_dobj = Union["Module", "Class", "Function", "Variable", "LibraryAttr"]


def is_function(obj: object) -> bool:
    """Return true if the object is a user-defined function."""
    return inspect.isroutine(obj)


def is_public(name: str) -> bool:
    return not name.startswith("_")


def filter_type(typ: Type[T], values: Iterable["Doc"]) -> List[T]:
    return [i for i in values if isinstance(i, typ)]


def find_kind(s: str) -> Optional[str]:
    match = re.search(r"{kind}`(.*?)`", s)
    if match:
        return match.group(1)
    return None


class Context(UserDict):
    whitelisted: Set[str]
    blacklisted: Set[str]

    def __init__(self) -> None:
        super().__init__()
        self.whitelisted = set()
        self.blacklisted = set()


class Doc:
    __slots__ = ("name", "obj", "docstring", "module")

    def __init__(
        self, name: str, obj: Any, docstring: Optional[str], module: "Module"
    ) -> None:
        self.name = name
        self.obj = obj
        self.docstring = docstring
        self.module = module

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.refname!r}>"

    @property
    def source(self) -> str:
        """
        Cleaned (dedented) source code of the Python object.
        If not available, an empty string.
        """
        try:
            return inspect.getsource(self.obj)
        except OSError:
            return ""

    @property
    def kind(self) -> str:
        """Identify every kind of object."""
        raise NotImplementedError

    @property
    def refname(self) -> str:
        """Refname of current object."""
        return self.name

    @property
    def qualname(self) -> str:
        """Qualified name of current object."""
        cls: Optional[Class] = getattr(self, "cls", None)
        if cls is None:
            return self.name
        return cls.name + "." + self.name

    @property
    def heading_id(self) -> str:
        return self.qualname.replace(".", "-")


class Module(Doc):
    __slots__ = (
        "supermodule",
        "doc",
        "context",
        "skipped_submodules",
        "var_comments",
        "overloads",
        "vcpicker",
    )
    obj: ModuleType
    doc: Dict[str, Union["Module", "Class", "Function", "Variable", "LibraryAttr"]]
    skipped_submodules: Set[str]
    var_comments: Dict[str, str]
    overloads: Dict[str, List[schema.OverloadFunctionDef]]

    def __init__(
        self,
        obj: Any,
        *,
        supermodule: Optional["Module"] = None,
        context: Optional[Context] = None,
    ) -> None:
        dobj: T_dobj
        if isinstance(obj, str):
            obj = import_module(obj)
        docstring = inspect.getdoc(obj)
        super().__init__(obj.__name__, obj, docstring, self)
        self.supermodule = supermodule
        self.context = Context() if context is None else context
        self.doc = {}
        self.skipped_submodules = set()

        # Add whitelisted, add blacklisted
        for name, condition in self.__autodoc__.items():
            if not name.startswith(self.refname + "."):
                # We rule that submodule `__autodoc__` can not control supermodule
                # convert qualname to refname
                name = f"{self.refname}.{name}"
            if condition is True or isinstance(condition, str):
                self.context.whitelisted.add(name)
            elif condition is False or condition is None:
                self.context.blacklisted.add(name)

        # Scan the package dir for subpackages
        if self.is_package:
            # TODO: handle namespace (extend namespace path and try import recursively)
            for _, name, ispkg in iter_modules(getattr(self.obj, "__path__")):
                if name in self.doc:
                    continue
                if not is_public(name) and not self.is_whitelisted(name):
                    continue
                if self.is_blacklisted(name):
                    self.skipped_submodules.add(name)
                    continue
                fullname = f"{self.name}.{name}"
                try:
                    module = import_module(fullname)
                except Exception:
                    print(f"ImportError: {fullname!r}")
                    continue
                m = Module(module, supermodule=self, context=self.context)
                self.doc[name] = m
                # Remove namespace without submodules
                if m.is_namespace and not m.doc:
                    del self.doc[name]
                    self.context.pop(m.refname)

        annotations: Dict[str, Any] = getattr(self.obj, "__annotations__", {})
        vcpicker = pycode.extract_all_comments(self.source)
        ofpicker = pycode.extract_all_overloads(self.source, globals=self.obj.__dict__)
        self.var_comments = vcpicker.comments
        self.vcpicker = vcpicker
        self.overloads = ofpicker.overloads

        # Find public members
        public_objs: Dict[str, Any] = {}
        for name, obj in self.obj.__dict__.items():
            if inspect.ismodule(obj):
                continue
            if self.is_whitelisted(name):
                public_objs[name] = obj
                continue
            if (
                is_public(name)
                and not self.is_blacklisted(name)
                and (self.is_from_current_module(obj) or name in vcpicker.comments)
            ):
                public_objs[name] = obj

        # Start construct of public objects
        for name, obj in public_objs.items():
            if obj is None:
                self.doc[name] = Variable(
                    name,
                    None,
                    self,
                    docstring=vcpicker.comments.get(name),
                    type_annotation=annotations.get(name),
                )
                continue
            if self.is_from_user_library(obj):
                # Override docstring from `__autodoc__: Dict[str, str]`
                # Writing user docstring in `__autodoc__` is recommended
                docstring = "三方库 API"
                _docstring = self.__autodoc__.get(name)
                if isinstance(_docstring, str):
                    docstring = inspect.cleandoc(_docstring)
                self.doc[name] = LibraryAttr(name, obj, docstring, self)
                continue
            if is_function(obj):
                if obj.__name__ == "<lambda>":
                    self.doc[name] = Variable(
                        name,
                        obj,
                        self,
                        docstring=vcpicker.comments.get(name),
                        type_annotation=annotations.get(name),
                    )
                else:
                    docstring = vcpicker.comments.get(name)
                    if docstring:
                        # dynamic function
                        obj.__doc__ = docstring
                    self.doc[name] = Function(name, obj, self)
            elif inspect.isclass(obj):
                docstring = vcpicker.comments.get(name)
                if docstring:
                    # dynamic class
                    obj.__doc__ = docstring
                self.doc[name] = Class(
                    name,
                    obj,
                    self,
                )
            else:
                self.doc[name] = Variable(
                    name,
                    obj,
                    self,
                    docstring=vcpicker.comments.get(name),
                    type_annotation=annotations.get(name),
                )

        # Find overload function from source code
        # Find stub file for a package
        if not self.is_namespace:

            for dfunction in self.functions(cls_level=True):
                if dfunction.qualname in self.overloads:
                    dfunction.overloads = self.overloads[dfunction.qualname]

            if not self.obj.__file__:
                raise
            pyi_path = Path(self.obj.__file__).with_suffix(".pyi")
            if pyi_path.exists():
                with open(pyi_path) as f:
                    pyi_source = f.read()
                overloads = pycode.extract_all_overloads(pyi_source).overloads
                public_names = public_objs.keys()
                comments = pycode.extract_all_comments(pyi_source).comments
                self.var_comments.update(comments)

                # Proper pyi source code should be executable
                _globals: Dict[str, Any] = {}
                # Performance relative import
                _globals["__name__"] = self.refname + (
                    ".__init__" if self.is_package else ""
                )
                exec(pyi_source, _globals)
                annotations.update(_globals.get("__annotations__", {}))
                _globals_public = {
                    i: v for i, v in _globals.items() if i in public_names
                }
                for name in annotations:
                    _globals_public.setdefault(name, ...)
                skip_keys = public_names - _globals_public.keys()
                if skip_keys:
                    print(
                        f"Found {skip_keys!r} in `{self.refname}` "
                        "but not found in its stub file",
                    )

                # Resolve object
                solved_variables: Dict[str, Variable] = {}
                solved_functions: Dict[str, Function] = {}
                solved_classes: Dict[str, Class] = {}
                for name, obj in _globals_public.items():
                    if name in skip_keys:
                        continue
                    if is_function(obj):
                        obj.__module__ = self.refname
                        # Frozen signature before change code object
                        obj.__signature__ = inspect.signature(obj)
                        # Magic trick the dummy code object point to the real code
                        if name not in overloads:
                            if not obj.__doc__:
                                obj.__doc__ = self.doc[name].docstring
                        else:
                            obj = self.doc[name].obj
                        solved_functions[name] = Function(
                            name, obj, self, overloads=overloads.get(name)
                        )
                    elif inspect.isclass(obj):
                        obj.__module__ = self.refname
                        solved_classes[name] = Class(name, obj, self)
                    else:
                        if name in self.doc:
                            obj = self.doc[name].obj
                        solved_variables[name] = Variable(
                            name,
                            obj,
                            self,
                            docstring=self.var_comments.get(name),
                            type_annotation=annotations.get(name),
                        )

                # Resolve class members
                for raw_cls in self.classes():
                    if raw_cls.name in skip_keys:
                        continue
                    solved_cls = solved_classes[raw_cls.name]
                    to_resolve_keys = raw_cls.doc.keys() & solved_cls.doc.keys()
                    for name in to_resolve_keys:
                        dobj = solved_cls.doc[name]
                        if isinstance(dobj, Function):
                            obj = dobj.obj
                            qualname = dobj.qualname
                            obj.__module__ = self.refname
                            obj.__signature__ = inspect.signature(obj)
                            if qualname not in overloads:
                                if not obj.__doc__:
                                    obj.__doc__ = raw_cls.doc[name].docstring
                            else:
                                obj = raw_cls.doc[name].obj
                            solved_cls.doc[name] = Function(
                                name,
                                obj,
                                self,
                                cls=solved_cls,
                                overloads=overloads.get(qualname),
                            )
                    for dobj in solved_cls.variables():
                        if not dobj.docstring:
                            dobj.docstring = self.var_comments.get(dobj.qualname)

                # Set pyi object
                self.doc.update(solved_variables)
                self.doc.update(solved_functions)
                self.doc.update(solved_classes)

        self.context[self.refname] = self
        for dobj in self.doc.values():
            self.context[dobj.refname] = dobj
            if isinstance(dobj, Class):
                for dobj2 in dobj.doc.values():
                    self.context[dobj2.refname] = dobj2

    @property
    def __autodoc__(self) -> Dict[str, Union[bool, str]]:
        return getattr(self.obj, "__autodoc__", {})

    def is_whitelisted(self, name: str) -> bool:
        return f"{self.refname}.{name}" in self.context.whitelisted

    def is_blacklisted(self, name: str) -> bool:
        return f"{self.refname}.{name}" in self.context.blacklisted

    @property
    def is_package(self) -> bool:
        return hasattr(self.obj, "__path__")

    @property
    def is_namespace(self) -> bool:
        return hasattr(self.obj, "__path__") and not self.obj.__file__

    def is_from_current_module(self, obj: Any) -> bool:
        mod = inspect.getmodule(inspect.unwrap(obj))
        if not mod:
            return False
        return mod.__name__ == self.obj.__name__

    def is_from_user_library(self, obj: Any) -> bool:
        if not (is_function(obj) or inspect.isclass(obj)):
            return False
        module = getattr(obj, "__module__", "")
        if module == "builtins":
            return False
        name1, name2 = self.name.split(".", 1)[0], module.split(".", 1)[0]
        if name2 == "typing":
            return False
        return name1 != name2

    def variables(self) -> List["Variable"]:
        return filter_type(Variable, self.doc.values())

    def functions(self, cls_level: bool = False) -> List["Function"]:
        """
        Args:
            cls_level: returns with class-level function.
        """
        result: List[Function] = filter_type(Function, self.doc.values())
        if cls_level:
            for c in self.classes():
                result.extend(filter_type(Function, c.doc.values()))
        return result

    def classes(self) -> List["Class"]:
        return filter_type(Class, self.doc.values())

    def libraryattrs(self) -> List["LibraryAttr"]:
        return filter_type(LibraryAttr, self.doc.values())

    def submodules(self) -> List["Module"]:
        return filter_type(Module, self.doc.values())

    @property
    def refname(self) -> str:
        return self.name


class Class(Doc):
    __slots__ = ("doc", "instance_vars", "var_comments")
    obj: type
    docstring: str
    doc: Dict[str, Union["Function", "Variable"]]
    instance_vars: Set[str]

    def __init__(self, name: str, obj: Any, module: "Module") -> None:
        docstring = inspect.cleandoc(getattr(obj, "__doc__", "") or "")
        super().__init__(name, obj, docstring, module)
        if self.name in self.module.vcpicker.nodoc_classes:
            self.docstring = ""
        self.doc = {}

        annotations: Dict[str, Any] = getattr(self.obj, "__annotations__", {})
        annotations_only: Set[str] = set()
        for name in annotations:
            if not hasattr(self.obj, name):
                annotations_only.add(name)

        if hasattr(self.obj, "__slots__"):
            instance_vars = set(getattr(self.obj, "__slots__", ()))
        elif self.source:
            # Get instance vars from source code
            source = dedent(self.source)  # avoid unexpected source indent in try block
            instance_vars = (pycode.extract_all_comments(source).instance_vars).get(
                self.name, set()
            )
            instance_vars |= annotations_only
        else:
            instance_vars = set(annotations_only)
        self.instance_vars = instance_vars
        var_comments = {
            k[len(self.qualname) + 1 :]: v
            for k, v in self.module.var_comments.items()
            if k.startswith(self.qualname + ".")
        }
        self.var_comments = var_comments

        if hasattr(self.obj, "__members__"):
            return

        public_objs: List[Class.Attribute] = []
        for name, kind, cls, obj in inspect.classify_class_attrs(self.obj):
            if cls is self.obj:
                if is_public(name) or self.is_whitelisted(name):
                    if self.is_blacklisted(name):
                        continue
                    if kind == "class method" or kind == "static method":
                        obj = obj.__func__
                    public_objs.append(Class.Attribute(name, kind, obj))

        # TODO: Filter and sort own member

        # Convert the public Python objects to documentation objects.
        for name, kind, obj in public_objs:
            if is_function(obj):
                self.doc[name] = Function(
                    name, obj, self.module, cls=self, method_type=kind
                )
            elif inspect.isclass(obj):
                pass
            else:
                # obj is instance descriptor created by __slots__, remove if not comment
                if not isinstance(obj, property) and name not in self.var_comments:
                    continue
                self.doc[name] = Variable(
                    name,
                    obj,
                    self.module,
                    docstring=var_comments.get(name),
                    cls=self,
                    type_annotation=annotations.get(name),
                )

        for name in var_comments:
            self.doc.setdefault(
                name,
                Variable(
                    name,
                    ...,
                    self.module,
                    docstring=var_comments[name],
                    cls=self,
                    type_annotation=annotations.get(name),
                ),
            )

    class Attribute(NamedTuple):
        name: str
        kind: str
        obj: Any

    # TODO: fix whitelist and blacklist from its class mro
    def is_whitelisted(self, name: str) -> bool:
        return f"{self.refname}.{name}" in self.module.context.whitelisted

    def is_blacklisted(self, name: str) -> bool:
        return f"{self.refname}.{name}" in self.module.context.blacklisted

    def variables(self) -> List["Variable"]:
        return filter_type(Variable, self.doc.values())

    def functions(self) -> List["Function"]:
        return filter_type(Function, self.doc.values())

    def params(self) -> str:
        """Returns string of signature without annotation and returns."""
        return utils.signature_repr(utils.get_signature(self.obj))

    @property
    def kind(self) -> str:
        if self.docstring:
            fromdoc = find_kind(self.docstring.split("\n", 1)[0])
            if fromdoc:
                return fromdoc
        if hasattr(self.obj, "__members__"):
            return "enum"
        if inspect.isabstract(self.obj):
            return "abstract class"
        return "class"

    @property
    def refname(self) -> str:
        return f"{self.module.refname}.{self.qualname}"


class Function(Doc):
    __slots__ = ("cls", "overloads", "method_type")
    obj: Callable

    def __init__(
        self,
        name: str,
        obj: Callable,
        module: "Module",
        *,
        cls: Optional[Class] = None,
        overloads: List[schema.OverloadFunctionDef] = None,
        method_type: str = "method",
    ) -> None:
        docstring = inspect.cleandoc(obj.__doc__ or "")
        super().__init__(name, obj, docstring, module)
        self.cls = cls
        self.overloads = overloads or []
        self.method_type = method_type

    def params(self) -> str:
        """Returns string of signature without annotation and returns."""
        return utils.signature_repr(utils.get_signature(self.obj))

    @staticmethod
    def is_async(obj: Callable) -> bool:
        return inspect.iscoroutinefunction(obj)

    @property
    def kind(self) -> str:
        if self.docstring:
            fromdoc = find_kind(self.docstring.split("\n", 1)[0])
            if fromdoc:
                return fromdoc
        builder = []
        if getattr(self.obj, "__isabstractmethod__", False):
            builder.append("abstract")
        if self.is_async(self.obj):
            builder.append("async")
        if self.cls:
            if self.method_type == "class method":
                builder.append("classmethod")
            elif self.method_type == "static method":
                builder.append("staticmethod")
            elif self.method_type == "property":
                builder.append("property")
            else:
                builder.append("method")
        else:
            builder.append("def")
        return " ".join(builder)

    @property
    def qualname(self) -> str:
        return f"{self.cls.name}.{self.name}" if self.cls is not None else self.name

    @property
    def refname(self) -> str:
        return f"{self.module.refname}.{self.qualname}"


class Variable(Doc):
    __slots__ = ("cls", "_type_annotation")
    _type_annotation: Optional[type]

    def __init__(
        self,
        name: str,
        obj: Any,
        module: "Module",
        *,
        docstring: Optional[str] = None,
        cls: Optional[Class] = None,
        type_annotation: Optional[type] = None,
    ) -> None:
        if isinstance(obj, property):
            docstring = inspect.cleandoc(obj.__doc__ or "")
        super().__init__(name, obj, docstring, module)
        self.cls = cls
        self._type_annotation = type_annotation

    @property
    def kind(self) -> str:
        if self.docstring:
            fromdoc = find_kind(self.docstring.split("\n", 1)[0])
            if fromdoc:
                return fromdoc
        if isinstance(self.obj, property):
            if getattr(self.obj, "__isabstractmethod__", False):
                return "abstract property"
            return "property"
        if self.cls:
            return (
                "instance-var" if self.name in self.cls.instance_vars else "class-var"
            )
        return "var"

    @property
    def type_annotation(self) -> str:
        if self._type_annotation is not None:
            return formatannotation(self._type_annotation)
        # class.__init__ assignment
        try:
            return utils.convert_anno_new_style(
                self.module.vcpicker.annotations[self.qualname]
            )
        except KeyError:
            pass
        if isinstance(self.obj, property):
            if sys.version_info <= (3, 7) and isinstance(self.cls, NamedTuple):
                # Before py3.7, NamedTuple member is property and abstract
                return formatannotation(
                    inspect.signature(self.cls.obj).parameters[self.name].annotation
                )
            return formatannotation(
                inspect.signature(self.obj.fget or self.obj.__get__).return_annotation
            )
        elif getattr(self.obj, "__module__", None) == "typing":
            return formatannotation(self.obj)
        return ""

    @property
    def qualname(self) -> str:
        return f"{self.cls.name}.{self.name}" if self.cls is not None else self.name

    @property
    def refname(self) -> str:
        return f"{self.cls.refname if self.cls else self.module.refname}.{self.name}"


class LibraryAttr(Doc):
    def __init__(self, name: str, obj: Any, docstring: str, module: "Module") -> None:
        super().__init__(name, obj, dedent(docstring).strip(), module)

    @property
    def kind(self) -> str:
        return "library-attr"

    @property
    def refname(self) -> str:
        return f"{self.module.refname}.{self.name}"
