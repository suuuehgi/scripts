#!/usr/bin/env -S uv run --no-project --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "anyascii",
# ]
# ///

from anyascii import anyascii

import argparse
from pathlib import Path
import re
import sys

# Characters to just remove from the input string
# ,'"?!¿¡ (it's -> its)
DROP_CHARS = re.compile(r'[,\'"\?\!¿¡]')

# (Subjective) replacements done first
# Regex sensitive! -- escape regex special characters
EXCEPTIONS = {
        'ß': 'ss',
        'ä': 'ae',
        'ö': 'oe',
        'ü': 'ue',
        'Ä': 'Ae',
        'Ö': 'Oe',
        'Ü': 'Ue',
        r'\. ': '_',
        r'\) ': '-',
        r' \(': '-',
        r'\] ': '-',
        r' \[': '-',
        r'\} ': '-',
        r' \{': '-',
        }

# Extension white-list of file extensions
# e.g. preserve `tar.gz`
COMPOUND_EXTENSIONS = {
        '.tar.gz',
        '.tar.bz2',
        '.tar.xz',
        '.tar.zst'
        }

COMPOUND_EXTENSIONS = { ext.lower() for ext in COMPOUND_EXTENSIONS }

def sanitize(s: str) -> str:
    '''
    Step 1: Perform special replacements
      E.g.: 'À Noël, où l’aïeul âgé brûla ça (final)' -> 'À Noël, où l’aïeul âgé brûla ça-final)'

    Step 2: Maps non-ASCII characters to their closest ASCII representation.
      E.g.: 'À Noël, où l’aïeul âgé brûla ça-final)' -> 'A Noel, ou l'aieul age brula ca-final)'

    Step 3: Remove DROP_CHARS.
      E.g.: 'A Noel, ou l'aieul age brula ca-final)' -> 'A Noel ou laieul age brula ca-final)'

    Step 4: Replace spaces by underscores.
      E.g.: 'A Noel ou laieul age brula ca-final)' -> 'A_Noel_ou_laieul_age_brula_ca-final)'

    Step 5: Replace remaining non-alphanumeric character with a dash, strip surrounding dashes, lower case
      E.g.: 'A_Noel_ou_laieul_age_brula_ca-final)' -> 'a_noel_ou_laieul_age_brula_ca-final'
    '''
    for pattern, replacement in EXCEPTIONS.items():
        s = re.sub(pattern, replacement, s)

    s = DROP_CHARS.sub('', anyascii(s))

    return re.sub(r'[^\w]+', '-', s.replace(' ', '_')).strip('-').lower()

def strconv(text: str) -> str:
    '''
    Sanitizes the string until the last period, if remainder not in COMPOUND_EXTENSIONS.

    E.g. 'this.beautiful.house.tar.gz' -> 'this-beautiful-house.tar.gz'
         'this-beautiful-house.rar.gz' -> 'this-beautiful-house-rar.gz'
    '''
    path = Path(text.strip())

    # Remove all suffixes
    # ''.join(path.suffixes) gives e.g. '.tar.gz'
    exts = [ ext.lower() for ext in path.suffixes ]
    stem = path.name[:-len( ''.join(exts) )]

    if not exts:
        return sanitize(path.name)

    # possible comp. ext.
    if len(exts) > 1:

        while len(exts) > 1:

            # Remaining ext. is allowed
            if ''.join(exts) in COMPOUND_EXTENSIONS:
                return sanitize(stem) + ''.join(exts)

            # Add next ext to stem
            # E.g. 'this.beautiful.house.tar.gz'
            # 'this' == stem <--'.beautiful'-- ['.beautiful', '.house', '.tar', '.gz'] == exts
            # stem == 'this.beautiful', exts = ['.house', '.tar', '.gz']
            else:
                stem = stem + exts.pop(0)

    return sanitize(stem) + exts[0]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Converts any Unicode string into file system safe ASCII.",
        epilog='Usage: strconv "My File.txt"  OR  echo "My File.txt" | strconv'
    )
    # nargs='*' allows 0 or more arguments (handles piped input cleanly)
    parser.add_argument("text", nargs="*", help="string to sanitize")

    args = parser.parse_args()

    # 1. Prefer command-line arguments over stdin
    if args.text:
        input_text = " ".join(args.text)

    # 2. Check if data is piped via stdin
    elif not sys.stdin.isatty():
        input_text = sys.stdin.read().rstrip('\r\n')
        if not input_text:
            sys.exit(0) # Empty pipe, exit silently

    # 3. No input provided
    else:
        parser.print_help(sys.stderr)
        sys.exit(1)

    print(strconv(input_text))
