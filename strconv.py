#!/usr/bin/python3

import sys, os

def strconv(text: str) -> str:
    """
    Transliterates German umlauts, replaces spaces and slashes with underscores,
    and drops remaining non-ASCII characters to generate safe directory names.
    """
    translate = {
        ' ':  '_',
        '/': '_',
        'ß': 'ss',
        'ä': 'ae',
        'ö': 'oe',
        'ü': 'ue',
        'Ä': 'Ae',
        'Ö': 'Oe',
        'Ü': 'Ue',
        "'":  None,
    }

    mapping = str.maketrans(translate)

    translated = text.translate(mapping)

    # 2. Drop any remaining non-ASCII characters
    return translated.encode('ascii', 'ignore').decode('ascii')

if __name__ == "__main__":
    name = os.path.basename(sys.argv[0])

    # 1. Print help if requested
    if len(sys.argv) > 1 and sys.argv[1] in ('-h', '--help'):
        print(f"{name} converts a string with spaces and non-ASCII into spaceless ASCII.\n")
        print(f"Usage: {name} \"<string>\" or echo \"<string>\" | {name}\n")
        print("\t-h, --help: Print help")
        sys.exit(0)

    # 2. Prefer command-line arguments over stdin
    if len(sys.argv) > 1:
        input_text = " ".join(sys.argv[1:])
    # 3. Check if data is piped via stdin
    elif not sys.stdin.isatty():
        input_text = sys.stdin.read().rstrip('\r\n')
    # 4. No input provided
    else:
        sys.stderr.write("Error: No input provided.\n")
        sys.exit(1)

    print(strconv(input_text))
