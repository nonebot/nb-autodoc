# type: ignore
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from mypkg import A

    class A_:
        ...


if ...:

    def a():
        ...


class B:
    if TYPE_CHECKING:
        from mypkg import f

        class B_:
            ...

        if ...:

            class B__:
                ...

        from mypkg import f2
