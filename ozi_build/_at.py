from dataclasses import dataclass
from typing import List
from typing import Optional

from ._char import Character  # noqa: TC002
from ._repeat import InfiniteRepeat
from ._repeat import Repeat


@dataclass
class EndOfString:
    character: Optional[Character] = None

    @property
    def starriness(self):
        return 0

    @property
    def minimum_length(self):
        return 1  # Meaningless really here

    def overall_character_class(self):
        return self.character

    def __repr__(self) -> str:
        return f"${self.character}"

    def __and__(self, other: Character) -> Optional[Character]:
        return other & self.character

    def example(self):
        return "\n"  # ish

    def set_character(self, previous_elems: List):
        """
        To force backtracking, the dollar will have to not match any
        previous groups until a mandatory group.
        This can perhaps be made more lenient.

        To cause backtracking on a long string of a's:
        a*a*a*$ -> Any [^a]
        [ab]+a*a*a*$ -> Any [^ab] (baaaaaaaaaaaab does not backtrack)
        b+a*a*a*$ -> Any [^a]
        .a*a*a*$ -> Any [^a]
        .+a*a*a*$ -> Cannot backtrack because everything gets matched by .+ :(
        """
        self.character = None
        for elem in reversed(previous_elems):
            if elem.minimum_length > 0 and not isinstance(elem, InfiniteRepeat):
                return  # xa*[ab]*a*$ -> [ab]
            c = (
                elem.maximal_character_class()
                if isinstance(elem, Repeat)
                else elem.overall_character_class()
            )
            if c:
                if elem.minimum_length > 0 and (self.character & c) != self.character:
                    # c is smaller than self.character (i.e. c is not an ANY)
                    # x+a*[ab]*a*$ -> [ab]
                    return
                self.character |= c
