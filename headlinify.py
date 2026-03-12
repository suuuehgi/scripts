#!/usr/bin/env python3
"""
Headline/title capitalization script.

Supports AP, APA, Chicago (default), and MLA styles.

Usage:
    python headline.py "your title here"             # Chicago (default)
    python headline.py "your title here" ap
    python headline.py "your title here" mla
    echo "your title here" | python headline.py -
    echo "your title here" | python headline.py - apa

Style rules (word capitalization, excluding first/last word):
    ap       Capitalize words with 4+ letters; lowercase everything shorter
    apa      Capitalize words with 5+ letters; lowercase everything shorter
    chicago  Capitalize major words; lowercase all articles, coordinating
             conjunctions, and prepositions (regardless of length)
    mla      Same as Chicago (MLA also lowercases all prepositions)

In all styles: first word, last word, and the first word after a
colon or em dash are always capitalized.
"""

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

CHICAGO_MINOR = ARTICLES | COORD_CONJ | PREPOSITIONS
MLA_MINOR     = ARTICLES | COORD_CONJ | PREPOSITIONS

# ── Helpers ────────────────────────────────────────────────────────────────

def _cap_first(word: str) -> str:
    """Uppercase the first alphabetic character in a word."""
    for i, ch in enumerate(word):
        if ch.isalpha():
            return word[:i] + ch.upper() + word[i + 1:]
    return word

def _bare(word: str) -> str:
    """Strip punctuation for word-list lookups (keeps apostrophes/hyphens)."""
    return re.sub(r"[^a-zA-Z'-]", "", word).lower()

def _after_break(prev: str) -> bool:
    """True if the previous token ended with a colon or em dash."""
    return bool(re.search(r"[:—]$", prev))

# ── Main function ──────────────────────────────────────────────────────────

def titlecase(text: str, style: str = "chicago") -> str:
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
        elif style == "ap":
            result.append(_cap_first(word) if len(b) >= 4 else word.lower())
        elif style == "apa":
            result.append(_cap_first(word) if len(b) >= 5 else word.lower())
        elif style == "chicago":
            result.append(word.lower() if b in CHICAGO_MINOR else _cap_first(word))
        elif style == "mla":
            result.append(word.lower() if b in MLA_MINOR else _cap_first(word))
        else:
            result.append(_cap_first(word))

    return " ".join(result)

# ── CLI ────────────────────────────────────────────────────────────────────

VALID_STYLES = ("ap", "apa", "chicago", "mla")

def main():
    parser = argparse.ArgumentParser(
        description="Apply headline/title-case capitalization to text.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "styles:\n"
            "  ap       capitalize words with 4+ letters\n"
            "  apa      capitalize words with 5+ letters\n"
            "  chicago  lowercase articles, coordinating conjunctions, prepositions\n"
            "  mla      same as chicago\n\n"
            "First word, last word, and word after a colon/em dash are always capitalized.\n\n"
            "examples:\n"
            '  python headline.py "the man with the golden gun"\n'
            '  python headline.py "going from bad to worse" ap\n'
            '  echo "your title here" | python headline.py -'
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
        help="capitalization style (default: chicago)",
    )
    args = parser.parse_args()

    lines = sys.stdin.read().splitlines() if args.text == "-" else [args.text]
    for line in lines:
        print(titlecase(line, args.style))

if __name__ == "__main__":
    main()
