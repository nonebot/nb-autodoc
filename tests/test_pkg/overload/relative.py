from typing import Any, Dict, Optional, Union, overload

from .typing import T_Type, T_Type2

ctx: Dict[str, Any] = {}


@overload
def overelative(a: T_Type, /, b: int) -> int:
    ...


@overload
def overelative(a: T_Type2, /, b: int, *, c: dict, d: dict = ctx, **kwargs: str) -> str:
    ...


def overelative(
    a: Union[T_Type, T_Type2],
    /,
    b: int,
    *,
    c: Optional[dict] = None,
    d: Optional[dict] = ctx,
    **kwargs: str,
) -> Union[str, int]:
    ...
