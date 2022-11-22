class A:
    a: int
    b: int
    """b docstring"""

    def __init__(self) -> None:
        self.a: str
        """a docstring"""
        self.b = 1
        """bad"""
