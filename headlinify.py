#!/usr/bin/env python3
import argparse
import re
import sys

# ── Word lists ─────────────────────────────────────────────────────────────

ARTICLES = {"a", "an", "the"}

COORD_CONJ = {"and", "but", "for", "nor", "or", "so", "yet"}

PREPOSITIONS = {
    "aboard", "about", "above", "across", "after", "against", "along",
    "amid", "amidst", "among", "amongst", "around", "as", "aside", "at",
    "atop", "before", "behind", "below", "beneath", "beside", "besides",
    "between", "beyond", "by", "circa", "concerning", "despite", "down",
    "during", "except", "for", "from", "given", "in", "inside", "into",
    "like", "minus", "near", "next", "of", "off", "on", "onto", "opposite",
    "out", "outside", "over", "past", "per", "plus", "regarding", "round",
    "since", "than", "through", "thru", "till", "to", "toward", "towards",
    "under", "underneath", "unlike", "until", "unto", "up", "upon",
    "versus", "via", "with", "within", "without",
}

# Common minor-word helper for MLA/Chicago: all preps, articles, coord. conj.
CHICAGO_MLA_MINOR = ARTICLES | COORD_CONJ | PREPOSITIONS

# APA: minor words = articles, coord. conjunctions, and short prepositions
#            (3 or fewer letters). Everything else is a major word.
APA_SHORT_PREP = {w for w in PREPOSITIONS if len(w) <= 3}
APA_MINOR = ARTICLES | COORD_CONJ | APA_SHORT_PREP

# AP: similar to APA but AP explicitly: capitalize preps/conj with 4+ letters;
#     lowercase articles and short preps/conj (<=3 letters).
AP_SHORT_PREP_CONJ = {w for w in PREPOSITIONS | COORD_CONJ if len(w) <= 3}
AP_MINOR = ARTICLES | AP_SHORT_PREP_CONJ


# ── Helpers ────────────────────────────────────────────────────────────────

def _cap_first(word: str) -> str:
    """Uppercase the first alphabetic character in a word."""
    for i, ch in enumerate(word):
        if ch.isalpha():
            return word[:i] + ch.upper() + word[i + 1 :]
    return word


def _bare(word: str) -> str:
    """Strip punctuation for word-list lookups (keeps apostrophes/hyphens)."""
    return re.sub(r"[^a-zA-Z'-]", "", word).lower()


def _after_break(prev: str) -> bool:
    """True if the previous token ended with a colon or em dash."""
    return bool(re.search(r"[:—]$", prev))


# ── Style-specific decision functions ─────────────────────────────────────-

def _is_minor_ap(bare: str, index: int, last: int) -> bool:
    """AP: minor words are articles and preps/conj of <=3 letters.

    Prepositions and conjunctions of 4+ letters are capitalized as major
    words (including "Over" in the fox sentence).
    """
    # First/last handled separately by force_cap
    return bare in AP_MINOR


def _is_minor_apa(bare: str, index: int, last: int) -> bool:
    """APA 7 title case: lowercase only minor words of <=3 letters.

    Major words are nouns, verbs, adjectives, adverbs, pronouns,
    and all words of four letters or more.
    We approximate by: if len(bare) <= 3 and in APA_MINOR -> minor.
    """
    return bare in APA_MINOR


def _is_minor_chicago(bare: str, index: int, last: int) -> bool:
    """Chicago 17: lowercase articles, coord. conjunctions, and prepositions.

    Length is *not* a factor; all prepositions are minor words
    (including "Over" and "Through"), except when first/last.
    """
    return bare in CHICAGO_MLA_MINOR


def _is_minor_mla(bare: str, index: int, last: int) -> bool:
    """MLA 9: lowercase articles, prepositions, and coord. conjunctions.

    MLA lowercases all prepositions not in first/last position,
    regardless of length ("Over" is lowercase in MLA, too).
    """
    return bare in CHICAGO_MLA_MINOR


# ── Main function ─────────────────────────────────────────────────────────-

def titlecase(text: str, style: str = "ap") -> str:
    """Return text formatted in title case according to style."""
    style = style.lower()
    words = text.split()
    if not words:
        return text

    n = len(words)
    result = []

    for i, word in enumerate(words):
        b = _bare(word)
        force_cap = (
            i == 0
            or i == n - 1
            or (i > 0 and _after_break(words[i - 1]))
            or not b
        )

        if force_cap:
            result.append(_cap_first(word))
            continue

        if style == "ap":
            minor = _is_minor_ap(b, i, n - 1)
        elif style == "apa":
            minor = _is_minor_apa(b, i, n - 1)
        elif style == "chicago":
            minor = _is_minor_chicago(b, i, n - 1)
        elif style == "mla":
            minor = _is_minor_mla(b, i, n - 1)
        else:
            minor = False

        if minor:
            result.append(word.lower())
        else:
            result.append(_cap_first(word))

    return " ".join(result)


# ── CLI ────────────────────────────────────────────────────────────────────

VALID_STYLES = ("ap", "apa", "chicago", "mla")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply headline/title-case capitalization to text.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "styles:\n"
            "  ap       AP Stylebook: capitalize preps/conj of 4+ letters;\n"
            "           lowercase articles and shorter preps/conj\n"
            "  apa      APA 7: capitalize major words and all words with\n"
            "           four or more letters; lowercase only short minor\n"
            "           words (<= 3 letters)\n"
            "  chicago  Chicago 17: lowercase articles, coordinating\n"
            "           conjunctions, and all prepositions (regardless of\n"
            "           length)\n"
            "  mla      MLA 9: same minor-word classes as Chicago;\n"
            "           lowercase all prepositions, conjunctions, articles\n\n"
            "First word, last word, and word after a colon/em dash are\n"
            "always capitalized.\n\n"
            "examples:\n"
            '  python headlinify.py "the man with the golden gun"\n'
            '  python headlinify.py "going from bad to worse" ap\n'
            '  echo "your title here" | python headlinify.py -'
        ),
    )

    parser.add_argument(
        "text",
        nargs="?",
        default="-",
        help='text to capitalize, or "-" to read from stdin (default: stdin)',
    )
    parser.add_argument(
        "style",
        nargs="?",
        default="ap",
        choices=VALID_STYLES,
        help="capitalization style (default: ap)",
    )

    args = parser.parse_args()

    lines = sys.stdin.read().splitlines() if args.text == "-" else [args.text]
    for line in lines:
        print(titlecase(line, args.style))


if __name__ == "__main__":
    main()
