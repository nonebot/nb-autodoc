import typing as t
import typing_extensions as te

a = t.Dict[str, str]

b: te.TypeAlias = "dict[str, str]"

# TODO: add this after ast unparse expr implemented
c: "te.TypeAlias" = "dict[str, str]"

d: int = 1

e = 1
