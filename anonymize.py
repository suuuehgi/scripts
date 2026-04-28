#!/usr/bin/env python3
import argparse
import logging
import sys
from pathlib import Path

try:
    import regex as re
except ImportError:
    print("Error: regex module not found. Install with: sudo dnf install python3-regex", file=sys.stderr)
    sys.exit(1)


DEFAULT_PATTERNS: dict[str, tuple[str, str]] = {
    'ipv4': (
        r'(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'                     # First 3 octets with dots (e.g., 192.168.1.)
        r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)',                             # Final octet (e.g., 255)
        '[IP]'),
    'ipv6': (
        r'(?<![\w:.])(?!::(?:[^\w:.]|$))'                                        # Isolate IP and reject standalone "::"
        r'(?:'                                                                   # Begin main match
        r'(?>(?>([a-f0-9]{1,4})(?>:(?1)){7}|'                                    # Standard uncompressed IPv6 (8 segments)
        r'(?!(?:[a-f0-9:]*[a-f0-9](?>:|$)){8,})((?1)(?>:(?1)){0,6})?::(?2)?)|'    # Compressed IPv6 (using ::)
        r'(?>(?>(?1)(?>:(?1)){5}:|(?!(?:[a-f0-9:]*[a-f0-9]:){6,})(?3)?::(?>((?1)(?>:(?1)){0,4}):)?)?' # IPv4-mapped IPv6 prefix
        r'(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])(?>\.(?4)){3}))'            # IPv4-mapped IPv4 suffix
        r')'                                                                     # End main match
        r'(?![\w:.])',                                                           # Trailing boundary
        '[IPv6]'),
    'mac': (
        r'(?:[0-9a-fA-F]{2}[:-]){5}'                                             # First 5 pairs separated by : or -
        r'[0-9a-fA-F]{2}',                                                       # Final 6th pair
        '[MAC]'),
    'email': (
        r'\b[A-Za-z0-9._%+-]+'                                                                 # Username part (e.g., john.doe)
        r'@[A-Za-z0-9.-]+\.'                                                                   # Domain part and dot (e.g., @example.)
        r'(?!(?:service|scope|slice|socket|target|timer|mount|automount|swap|path|device)\b)' # Forbid systemd units (drops .service, .scope, etc.)
        r'[A-Za-z]{2,}\b',                                                                      # Top-Level Domain (e.g., com, uk)
        '[EMAIL]'),
    'uuid': (
        r'\b[0-9a-fA-F]{8}-'                                                     # 8 hex digits
        r'[0-9a-fA-F]{4}-'                                                       # 4 hex digits
        r'[0-9a-fA-F]{4}-'                                                       # 4 hex digits
        r'[0-9a-fA-F]{4}-'                                                       # 4 hex digits
        r'[0-9a-fA-F]{12}\b',                                                    # 12 hex digits
        '[UUID]'),
    'url':    (
        r"\b(?:[A-Za-z]{3,9}://|www\.)"                                        # Scheme (http://, ftp://) or www. prefix
        r"(?:[A-Za-z0-9_.-]+(?::[A-Za-z0-9_.-]+)?@)?"                          # Optional user/password auth (user:pass@)
        r"[A-Za-z0-9.-]+"                                                      # Hostname (example.com)
        r"(?::\d+)?"                                                           # Optional port (:8080)
        r"(?:(?:/[A-Za-z0-9_\-\.~!*'();:@&=+$,/?#%]*[A-Za-z0-9_\-~/#+=%])|/)?",# Optional path/query/hash, ensuring it ends cleanly (/path?q=1#top)
        '[URL]'),
    'jwt': (
        r'\beyJ[A-Za-z0-9_-]+\.'                                                 # JWT Header (eyJ = base64 for '{"')
        r'[A-Za-z0-9_-]+\.'                                                      # JWT Payload
        r'[A-Za-z0-9_-]+\b',                                                     # JWT Signature
        '[JWT]'),
    'apikey': (
        r'(?:api[_-]?key|apikey|token)'                                          # Keyword indicating a secret
        r'[=:\s]+'                                                               # Separator (equals, colon, space)
        r'[\'"]?'                                                                # Optional opening quote
        r'[A-Za-z0-9_-]{20,}'                                                    # The actual key (20+ chars)
        r'[\'"]?',                                                               # Optional closing quote
        '[APIKEY]'),
}

IP_ALIASES: frozenset[str] = frozenset({'ipv4', 'ipv6'})


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def resolve_disabled(disabled: list[str]) -> set[str]:
    """Resolve disable list, expanding 'ip' alias to 'ipv4' and 'ipv6'.

    Args:
        disabled: List of pattern names to disable, may contain 'ip' as alias

    Returns:
        Set of resolved pattern names to disable
    """
    result = set()
    for name in disabled:
        if name == 'ip':
            result |= IP_ALIASES
        else:
            result.add(name)
    return result


def compile_pattern(pattern_str: str, replacement: str, ignore_case: int, name: str, line_num: int | None = None, source: str = '') -> tuple[re.Pattern, str, str]:
    """Compile a single regex pattern.

    Args:
        pattern_str: Regex pattern string
        replacement: Replacement string
        ignore_case: Regex compile flag
        name: Name of the pattern for reporting
        line_num: Optional line number for error reporting
        source: Optional source file name for error reporting

    Returns:
        Tuple of compiled pattern, replacement string, and name

    Raises:
        ValueError: If the regex is invalid
    """
    try:
        return (re.compile(pattern_str, ignore_case), replacement, name)
    except re.error as e:
        location = f" at line {line_num} in {source}" if line_num else ""
        raise ValueError(f"Invalid regex{location}: {pattern_str}\nError: {e}")


def get_default_patterns(disabled: set[str], ignore_case: int) -> list[tuple[re.Pattern, str, str]]:
    """Get default sensitive data patterns, excluding any disabled ones.

    Args:
        disabled: Set of resolved pattern names to exclude
        ignore_case: Regex compile flag

    Returns:
        List of compiled regex patterns, their replacements, and names
    """
    return [
        compile_pattern(pattern_str, replacement, ignore_case, name)
        for name, (pattern_str, replacement) in DEFAULT_PATTERNS.items()
        if name not in disabled
    ]


def load_patterns(pattern_file: Path, ignore_case: int) -> list[tuple[re.Pattern, str, str]]:
    """Load custom patterns from a config file.

    Each non-comment line must have the format 'pattern|replacement'.
    The separator is the last '|' in the line, allowing regex alternation
    in the pattern. A plain comma-separated list of words (no regex special
    characters) is automatically converted to a word-boundary alternation.

    Args:
        pattern_file: Path to pattern file
        ignore_case: Regex compile flag

    Returns:
        List of compiled regex patterns, their replacements, and source names

    Raises:
        FileNotFoundError: If pattern file does not exist
        ValueError: If a line is missing the separator or contains an invalid regex
    """
    if not pattern_file.exists():
        raise FileNotFoundError(f"Pattern file not found: {pattern_file}")

    patterns = []
    with open(pattern_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            if '|' not in line:
                raise ValueError(f"Missing separator at line {line_num} in {pattern_file}")

            last_pipe = line.rfind('|')
            pattern_str = line[:last_pipe]
            replacement = line[last_pipe + 1:]

            if ',' in pattern_str and not any(c in pattern_str for c in r'[]()+*?\^${}'):
                words = [w.strip() for w in pattern_str.split(',')]
                pattern_str = r'\b(?:' + '|'.join(re.escape(w) for w in words) + r')\b'

            name = f"line {line_num} in {pattern_file.name}"
            patterns.append(compile_pattern(pattern_str, replacement, ignore_case, name, line_num, str(pattern_file)))

    return patterns


def make_case_preserving_replacer(replacement: str):
    """Create a replacement function that mirrors the case pattern of each match.

    Handles three cases: all-uppercase, title-case (first letter upper), and lowercase.
    Replacements not starting with a letter (e.g. '[EMAIL]') are returned as-is.

    Args:
        replacement: The base replacement string

    Returns:
        A callable suitable for re.Pattern.sub()
    """
    def replacer(match: re.Match) -> str:
        matched = match.group()
        # Don't change capitalization if the match does not start with a letter, e.g. [URL], or 12345...
        if not matched or not replacement[0].isalpha():
            return replacement
        # HELLO --> WORLD
        if matched.isupper():
            return replacement.upper()
        # Jane Street 43 --> Johns Street 1
        # or
        # Jane --> John for "jane|john" in user config (preserve capitalization)
        if matched[0].isupper():
            return replacement[0].upper() + replacement[1:]
        return replacement
    return replacer


def anonymize_line(line: str, patterns: list[tuple[re.Pattern, str, str]]) -> str:
    """Apply all patterns to anonymize a single line.

    Case of each match is mirrored in the replacement: all-uppercase matches
    produce uppercase replacements, title-case matches produce capitalized
    replacements. Replacements not starting with a letter are returned as-is.

    Args:
        line: Input line to anonymize
        patterns: List of compiled regex patterns, their replacements, and names

    Returns:
        Line with all pattern matches replaced
    """
    result = line
    for pattern, replacement, _ in patterns:
        result = pattern.sub(make_case_preserving_replacer(replacement), result)
    return result


def check_line(line: str, patterns: list[tuple[re.Pattern, str, str]]) -> list[str]:
    """Find all pattern matches in a line without replacing.

    Args:
        line: Input line to check
        patterns: List of compiled regex patterns, replacements, and names

    Returns:
        List of matched strings, formatted as "(name): match"
    """
    return [f"({name}): {match.group()}" for pattern, _, name in patterns for match in pattern.finditer(line)]


def process_stream(input_stream, output_stream, patterns: list[tuple[re.Pattern, str, str]], check_mode: bool) -> None:
    """Process input stream line by line and write results to output stream.

    Args:
        input_stream: Readable input stream
        output_stream: Writable output stream
        patterns: List of compiled regex patterns, their replacements, and names
        check_mode: If True, report matches only without modifying the input
    """
    line_num = 0
    match_count = 0

    for line in input_stream:
        line_num += 1

        if check_mode:
            matches = check_line(line, patterns)
            if matches:
                match_count += 1
                output_stream.write(f"Line {line_num} {', '.join(matches)}\n")
        else:
            output_stream.write(anonymize_line(line, patterns))

    if check_mode:
        output_stream.write(f"\nFound matches in {match_count} of {line_num} lines\n")


def main() -> int:
    setup_logging()

    default_pattern_file = Path.home() / '.config' / 'anonymize.conf'
    valid_names = ', '.join(list(DEFAULT_PATTERNS.keys()) + ['ip'])

    parser = argparse.ArgumentParser(
        description='Anonymize sensitive data in log files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f'''Examples:
  %(prog)s input.log > output.log
  %(prog)s input.log -o output.log
  %(prog)s --check input.log
  %(prog)s -d ip email input.log
  %(prog)s -r "\\bfoo\\b" "[BAR]" -r "\\bbaz\\b" "[QUX]" input.log
  cat input.log | %(prog)s --no-user-config

Default pattern file: {default_pattern_file}
Available default pattern names: {valid_names}

Pattern file format:
  john,jane,joe|[USERNAME]
  company-project|[PROJECT]
  anthony|john
  # Comments start with #
Note: lower/Title/UPPER case of each match is being mirrored. E.g. "Anthony was scratching his ..." -> "John was scratching his ..."
        '''
    )

    parser.add_argument('file', type=Path, nargs='?', help='Input file (if not using stdin)')
    parser.add_argument('-o', '--output', type=Path, help='Output file (default: stdout)')
    parser.add_argument('-p', '--patterns', type=Path, help='Custom pattern file')
    parser.add_argument('--check', action='store_true', help='Check mode: find matches without replacing')
    parser.add_argument('-D', '--no-defaults', action='store_true', help='Disable all default patterns')
    parser.add_argument('-d', '--disable', action='append', metavar='NAME',
                        choices=list(DEFAULT_PATTERNS.keys()) + ['ip'],
                        default=[], help=f'Disable specific default patterns ({valid_names}); "ip" disables both ipv4 and ipv6')
    parser.add_argument('-r', '--replace', nargs=2, metavar=('PATTERN', 'REPLACEMENT'),
                        action='append', default=[], help='Add inline replacement (repeatable)')
    parser.add_argument('-i', '--case-sensitive', action='store_true', help='Enable case-sensitive matching (default: insensitive)')
    parser.add_argument('--no-user-config', action='store_true', help=f'Skip loading {default_pattern_file}')

    args = parser.parse_args()

    has_stdin = not sys.stdin.isatty()
    has_file = args.file is not None

    if has_file and has_stdin:
        logging.error("Cannot read from both standard input and a file. Please provide only one.")
        return 1
    if not has_file and not has_stdin:
        parser.print_help()
        logging.error("\nNo input provided. Provide a file argument or pipe data to standard input.")
        return 1

    try:
        ignore_case = re.IGNORECASE if not args.case_sensitive else 0
        disabled = resolve_disabled(args.disable)

        patterns = [] if args.no_defaults else get_default_patterns(disabled, ignore_case)

        if args.patterns:
            patterns.extend(load_patterns(args.patterns, ignore_case))
        elif not args.no_user_config and default_pattern_file.exists():
            patterns.extend(load_patterns(default_pattern_file, ignore_case))

        for idx, (pattern_str, replacement) in enumerate(args.replace, 1):
            patterns.append(compile_pattern(pattern_str, replacement, ignore_case, f"inline replace {idx}"))

        if not patterns:
            logging.error("No patterns defined")
            return 1

        with (open(args.file, 'r') if args.file else sys.stdin) as input_stream, \
             (open(args.output, 'w') if args.output else sys.stdout) as output_stream:
            process_stream(input_stream, output_stream, patterns, args.check)

        return 0

    except (FileNotFoundError, ValueError) as e:
        logging.error(str(e))
        return 1
    except Exception as e:
        logging.exception(f"Unexpected error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
