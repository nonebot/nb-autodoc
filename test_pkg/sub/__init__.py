from typing import Union


class OtherClass:
    """
    i am class under submodule
    """

    def a(self, a: str, b: int) -> str:
        """
        the args of this function will be automatically documented
        """
        ...

    def b(self, **kwargs: str) -> Union[str, int]:
        ...
