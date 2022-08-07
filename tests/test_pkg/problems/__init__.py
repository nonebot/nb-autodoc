from typing import List


class A:
    cls_attr: List = []
    """cls_attr docstring"""
    inst1: str
    """inst1 docstring"""
    inst_no_doc: str
    inst3: str = "inst3var"
    """inheritlink inst3"""

    @property
    def descriptor_no_doc(self) -> str:
        ...

    @property
    def descriptor_with_doc(self) -> str:
        """property docstring"""
        ...


class A2(A):
    __slots__ = ("inst2",)
    inst2: str
