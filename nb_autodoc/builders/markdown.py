from nb_autodoc.builders import Builder, MemberIterator


class MarkdownBuilder(Builder):
    def get_suffix(self) -> str:
        return "/.md"

    def text(self, itor: MemberIterator) -> str:
        return super().text(itor)

    # replace ref
    # ref: r"{(?P<name>\w+?)}`(?:(?P<text>[^{}]+?) <)?(?P<content>[\w\.]+)(?(text)>)`"
