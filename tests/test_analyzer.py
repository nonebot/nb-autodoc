from nb_autodoc.analyzer import convert_annot


def test_annot_unparser():
    assert (
        convert_annot("Union[List[int], Tuple[int], Set[int], Dict[str, int]]")
        == "list[int] | tuple[int] | set[int] | dict[str, int]"
    )
    assert convert_annot("Optional[str]") == "str | None"
    assert convert_annot("Callable[..., str]") == "(*Any, **Any) -> str"
    assert (
        convert_annot("Callable[[int, str], Callable[[str], Callable[[], None]]]")
        == "(int, str) -> (str) -> () -> None"
    )
    assert (
        convert_annot("Union[Callable[[], Optional[str]], str, None]")
        == "() -> (str | None) | str | None"
    )
