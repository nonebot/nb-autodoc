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


class Foo:
    """Foo summary

    main class for test_pkg

    Attributes:
        attr_ins: the instance variable
        attr_class: the class variable which not support documented
    """

    attr_class: int

    def __init__(self) -> None:
        self.attr_ins: int = 100

    def publicfunc(
        self,
        arg1: Api,
        arg2: Type["Api"],
        new_style1: Union[List[int], Tuple[int], Set[int], Dict[str, int]],
        new_style2: Union[Callable[[], Optional[str]], str, None],
        *,
        arg3: Type["Api2"]
    ) -> Api:
        """
        description for publicfunc

        Version: 1.1.0+

        Args (1.1.0+):
            arg1: desc1
            arg2 (Union[str, test_pkg.api.Api]) {version}`1.1.0+`: desc2
            arg3 {version}`1.1.0+`: desc3

        Returns:
            simply description for returns.
                maybe complex
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
    def iamclass(cls) -> None:
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
