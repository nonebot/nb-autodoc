"""
此包直接 import tests.simple_pkg 调用即可，内部链接全部为相对引用。

- `xx` -> {ref}`xx.xx`

版本的替换测试 {version}`1.1.0+`

相对模块链接替换测试 {ref}`.api.Api`
`.api.Api`: {ref}`.api.Api`
`repr`: {ref}``repr` <test>`
multiple `.api.Api`: {ref}`xx.xx <.api.Api>` some text {ref}`xx.xx <.api.Api>`
no replace: {ref}``noreplace` <xx> <.api.Api>` some text {ref}

FrontMatter:
    sidebar: auto
    option:
        a: b
"""
from typing import (
    TYPE_CHECKING,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
)

from .api import Api

if TYPE_CHECKING:
    from .api import Api2


var: int = 1
"""Api: short description.

firstline is origin google style docstring for override.

用法:
    xxx
"""


var3: int = 1
"""{ann}`Optional[Api]` {kind}`property`

override annotation and object kind in firstline.
"""


class Foo:
    """Foo summary.

    main class of simple_pkg.

    Attributes:
        attr_class (Api): the class variable comment
    """

    attr_class: int = 1

    def __init__(self) -> None:
        self.attr_ins: int = 100
        """the instance variable"""

    def publicfunc(
        self,
        arg1: Api,
        arg2: Type["Api"],
        new_style1: Union[List[int], Tuple[int], Set[int], Dict[str, int]],
        new_style2: Union[Callable[[], Optional[str]], str, None],
        *,
        arg3: Type["Api2"],
    ) -> Api:
        """description.

        Version: 1.1.0+

        Args (1.1.0+):
            arg1 (Optional[test_pkg.Foo.publicfunc]): descr1
            arg2 (Union[str, test_pkg.api.Api]) {version}`1.1.0+`: descr2
            arg3 {version}`1.1.0+`: descr3 with long description
                - `"a"`: literal "a"
                - `"b"`: literal "b"

        Returns:
            simply description for returns.
        """
        ...

    @staticmethod
    def iamstatic() -> Type["Api2"]:
        ...

    @classmethod
    def iamclass(cls) -> Callable[..., int]:
        ...

    def privatefunc(self) -> None:
        """Internal."""
        ...

    def __call__(self) -> None:
        """Public __call__."""
        ...


__autodoc__ = {"Foo.__call__": True, "Foo.privatefunc": False}
