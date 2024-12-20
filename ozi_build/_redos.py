import logging
from dataclasses import dataclass
from typing import Iterator, List, Optional

from ._at import EndOfString
from ._branch import Branch
from ._char import Character
from ._repeat import InfiniteRepeat, Repeat
from ._sequence import Sequence


@dataclass(frozen=True)
class Redos:
    starriness: int
    prefix_sequence: Sequence
    redos_sequence: Sequence
    repeated_character: Character
    killer: Optional[Character]

    @property
    def example_prefix(self) -> str:
        return self.prefix_sequence.example()

    def example(self, js_flavour: bool = False) -> str:
        repeated_char = self.repeated_character
        killer = self.killer
        # Try to find a repeating character which is also a killer
        if killer and (killing_repeat := repeated_char & killer):
            repeated_char = killing_repeat
            killer = None

        prefix = (
            self.example_prefix.encode("unicode_escape").decode().replace("'", "\\'")
        )
        repeated_char_s = (
            repeated_char.example()
            .encode("unicode_escape")
            .decode()
            .replace("'", "\\'")
        )
        e = f"'{prefix}' + " if prefix else ""
        if js_flavour:
            e += f"'{repeated_char_s}'.repeat(3456)"
        else:
            e += f"'{repeated_char_s}' * 3456"

        if killer:
            killer_s = (
                killer.example().encode("unicode_escape").decode().replace("'", "\\'")
            )
            return e + f" + '{killer_s}'"
        return e


def find(sequence, flags: int = 0) -> List[Redos]:
    """
    Returns Redos objects sorted by severity (most starry first), then sorted by example_prefix (shortest first).
    """
    redos = []
    for r in find_redos(sequence):
        if r not in redos:
            redos.append(r)
    return sorted(redos, key=lambda r: -r.starriness * 1000 + len(r.example_prefix))


def expand_branches(seq: Sequence) -> Iterator[Sequence]:
    """
    This could blow up exponentially, but it's nicer for now to expand branches.
    """
    head = []
    for i, elem in enumerate(seq.elements):
        if isinstance(elem, Branch):
            for b in elem.get_branches():
                head_plus_branch = head + (
                    [] if not b else [b] if not isinstance(b, Sequence) else b.elements
                )
                for tail in expand_branches(Sequence(seq.elements[i + 1 :])):
                    yield Sequence(head_plus_branch + tail.elements)
            return  # All processing in yields
        elif isinstance(elem, Repeat) and elem.starriness > 10:
            logging.debug("Exponential: %s", elem)
            if isinstance(elem.repeat, (Sequence, Branch)):
                for tail in expand_branches(Sequence(seq.elements[i + 1 :])):
                    yield Sequence(head + [elem] + tail.elements)
                    for pseudo_repeat in elem.repeat.matching_repeats():
                        logging.debug("Pseudo repeat %s", pseudo_repeat)
                        yield Sequence(
                            head + [elem.alter_repeat(pseudo_repeat)] + tail.elements
                        )
            else:
                head.append(elem)
        else:
            head.append(elem)
    yield Sequence(head)


def find_redos(sequence_with_branches) -> Iterator[Redos]:
    logging.debug(sequence_with_branches)
    if not isinstance(
        sequence_with_branches, Sequence
    ):  # singleton like Branch (ab|cd)
        sequence_with_branches = Sequence([sequence_with_branches])
    for seq in expand_branches(sequence_with_branches):
        yield from find_redos_in_branchless_sequence(seq)


def find_redos_in_branchless_sequence(seq: Sequence) -> Iterator[Redos]:
    logging.debug(seq)
    for i, elem in enumerate(seq.elements):
        # TODO branches
        if isinstance(elem, InfiniteRepeat) and (c := elem.overall_character_class()):
            yield from make_redos(seq, i, i + 1, c, elem.starriness)


def make_redos(
    seq: Sequence,
    sequence_start: int,
    continue_from: int,
    repeated_character: Character,
    starriness: int,
) -> Iterator[Redos]:
    # TODO branches
    character_history = [repeated_character]
    logging.debug(
        "Make ReDoS %d %d %s %d",
        sequence_start,
        continue_from,
        repeated_character,
        starriness,
    )
    for current_index in range(continue_from, len(seq)):
        elem = seq.elements[current_index]

        if isinstance(elem, EndOfString):
            # May need to go back before the matching sequence to calculate $
            elem.set_character(seq.elements[:current_index])

        eoc = elem.overall_character_class()
        new_c = repeated_character & eoc
        logging.debug("%s & %s = %s (for %s)", repeated_character, eoc, new_c, elem)

        # Handle optional elements
        if elem.minimum_length == 0:
            if elem.starriness:
                # If we have a*, we branch and try with and without it
                if new_c != repeated_character:
                    # Only branch if we have [ab]a* : if we have aa* or a[ab]* then the character class doesn't change
                    # Try without this element
                    yield from make_redos(
                        seq,
                        sequence_start,
                        current_index + 1,
                        repeated_character,
                        starriness,
                    )
            else:
                continue  # Don't care about finite repeats (abc)? or a{,4}

        # print(repeated_character, "+", elem.overall_character_class(), "->", new_c)
        if new_c is None:
            # This element will force backtracking as it's incompatible with `repeated_character`
            if elem.minimum_length and starriness > 2:
                yield redos_found(
                    seq,
                    sequence_start,
                    current_index,
                    repeated_character,
                    starriness,
                    None,
                )
            return

        starriness += elem.starriness
        repeated_character = new_c
        character_history.append(new_c)

    # Everything matched! We need to work backwards and find a 'killer' to cause backtracking if we want ReDoS
    logging.debug("Backtracking: %s", character_history)
    for current_index in reversed(range(continue_from, len(seq))):
        elem = seq.elements[current_index]
        character_history.pop()
        starriness -= elem.starriness
        if starriness <= 2:
            return
        # Can't get backtracking by not matching optional groups
        if elem.minimum_length > 0:
            # Find a character which matches the sequence and then fails on the killer
            if (match := elem.overall_character_class()) and (killer := match.negate()):
                old_repeat = character_history.pop()
                logging.debug(
                    "%s (for %s): killer=%s, repeat=%s",
                    match,
                    elem,
                    killer,
                    old_repeat,
                )
                yield redos_found(
                    seq,
                    sequence_start,
                    current_index,
                    old_repeat,
                    starriness,
                    killer,
                )
                return
    logging.debug("Backtracking: FAIL")


def redos_found(
    seq: Sequence,
    start: int,
    backtrack_at: int,
    repeated_character: Character,
    starriness: int,
    killer: Optional[Character],
) -> Redos:
    # TODO: Try to include some skipped optional parts (like `?`) just to make it nicer
    logging.debug("ReDoS found")
    return Redos(
        starriness,
        Sequence(seq.elements[:start]),
        Sequence(seq.elements[start : backtrack_at + 1]),
        repeated_character,
        killer,
    )