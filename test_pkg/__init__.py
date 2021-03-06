"""
快捷导入: 不匹配不会被认为是 Annotation

- `xx` -> {ref}`xx.xx`

版本的替换测试 {version}`1.1.0+`

模块链接替换测试 {ref}`test_pkg.api.Api`
{ref}`test_pkg.api.Api`
{ref}``sx` <not.replace>`
{ref}`xx.xx <test_pkg.api.Api>` some text {ref}`xx.xx <test_pkg.api.Api>`
{ref}``text` <xx> <xx.xx> <test_pkg.api.Api>` some text {ref}`ss`ticked` <test_pkg.api.Api>`
{ref}`test_pkg.api.Api` some text {ref}`ss`ticked` <test_pkg.api.Api>`
`{ref}`xx.xx <test_pkg.api.Api>`` so <ss> ss {ss}me {ref}`xx.xx` text {ref}`xx.xx <test_pkg.api.Api>`

Meta:
    sidebar: auto
    option:
        a: b
"""
from typing import (
    List,
    Tuple,
    Set,
    Dict,
    Union,
    Callable,
    Optional,
    Type,
    TYPE_CHECKING,
)

from test_pkg.api import Api

if TYPE_CHECKING:
    from test_pkg.api import Api2


var: int = 1
"""Context[int]: short description.

ahead is origin google style docstring for override.

用法:
    xxx
"""


var2: int = 1
"""Context[int] {kind}`AnyVar` {version}`1.1.0+`

ahead is complex support for type annotation (optional) and object mark.
before first Role is anno.
"""


var3: int = 1
"""{anno}`Optional[test_pkg.api.Api]` {kind}`AnyVar` {version}`1.1.0+`

anno could also write in a Role, but its priority is lowest.
"""


class Foo:
    """Foo summary

    main class for test_pkg

    Attributes:
        attr_class: the class variable text documented in other-attr
    """

    attr_class: int

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
        arg3: Type["Api2"]
    ) -> Api:
        """{version}`1.2.0+`

        description for publicfunc, version should be 1.2.0+

        Version: 1.1.0+

        Args (1.1.0+):
            arg1 (Optional[test_pkg.Foo.publicfunc]): desc1
            arg2 (Union[str, test_pkg.api.Api]) {version}`1.1.0+`: desc2
            arg3 {version}`1.1.0+`: desc3
                - `"a"`: literal "a"
                - `"b"`: literal "b"

        Returns:
            simply description for returns.
                - case1: case1desc
                - case2: case2desc
        """
        ...

    def multireturnsfunc(self, **kwargs: str) -> Union[str, int]:
        """
        the usage of `Foo.iamstatic` and `Api2`

        Returns:
            str: desc1
            str: desc2
        """
        ...

    @staticmethod
    def iamstatic() -> Type["Api2"]:
        """
        i am static~
        """
        ...

    @classmethod
    def iamclass(cls) -> Callable[..., int]:
        """
        i am class~
        """
        ...

    def innerfunc(self) -> None:
        """
        this should not documented
        """
        ...


__autodoc__ = {"Foo.innerfunc": False}
