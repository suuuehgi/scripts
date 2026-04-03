#!/usr/bin/env python3
import argparse
import ast
import fnmatch
import os
import re
import subprocess
import sys

HELP_TEXT = """\
tagsearch — Search indexed files by tags and Dublin Core dates via Baloo.

USAGE
    tagsearch '<query>'

QUERY SYNTAX
    Tags        Prefix with #. Tags may contain letters, digits,
                underscores, and hyphens.
                    #medical    #invoice    #my_scan

    Operators   and  or  not  ( )
                Case-insensitive. Consecutive terms automatically chain with 'and'.
                    #medical #invoice         →  #medical and #invoice
                    #medical not #invoice     →  #medical and not #invoice

    Date        Variable 'date' compared with  ==  !=  <  <=  >  >=
                ISO 8601 strings, compared lexicographically.
                Shell-style globs supported (*, ?, []). Quoting is optional.
                    date == 2025-*        any date in 2025
                    date == 2025-*-02     every 2nd of any month in 2025
                    date >= 2025-06       from June 2025 onward

CONSTRAINTS
    At least one positive (non-negated) #tag must appear in the query.
    Files without user.dublincore.date are excluded when date is used.

EXAMPLES
    tagsearch '#medical #invoice'
    tagsearch '#medical not #invoice'
    tagsearch '#medical and date >= 2025'
    tagsearch '#medical and date == 2025-*-02'
    tagsearch '(#medical or #health) not #invoice and date >= 2025-01-01'
"""

class QueryError(Exception):
    """Raised for syntax errors or missing dependencies."""
    pass

class MissingDate:
    """Null object: all comparisons return False (SQL NULL semantics)."""
    _f = lambda self, o: False
    __lt__ = __le__ = __gt__ = __ge__ = __eq__ = __ne__ = _f

class DateObj(str):
    """String subclass with shell-glob support in == and !=."""
    def __eq__(self, other):
        if isinstance(other, str) and re.search(r'[*?\[]', other):
            return fnmatch.fnmatch(self, other)
        return super().__eq__(other)

    def __ne__(self, other):
        return not self.__eq__(other)

# The strict whitelist of permitted AST nodes for query evaluation.
ALLOWED_NODES = {
    ast.Expression,
    ast.BoolOp, ast.And, ast.Or,
    ast.UnaryOp, ast.Not,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.Name, ast.Load,
    ast.Constant
}

class QueryValidator(ast.NodeVisitor):
    """
    Traverses the AST to:
    1. Ensure no unsupported syntax (like Lists or Attributes) is evaluated.
    2. Reject unknown variable names with a helpful error message.
    3. Extract tags that are not strictly negated.
    """
    def __init__(self):
        self.positive_vars = set()
        self.negated = False

    def visit(self, node):
        if type(node) not in ALLOWED_NODES:
            raise QueryError(f"Unsupported query syntax: {type(node).__name__}")
        super().visit(node)

    def visit_UnaryOp(self, node):
        if isinstance(node.op, ast.Not):
            old = self.negated
            self.negated = not self.negated
            self.visit(node.operand)
            self.negated = old
        else:
            raise QueryError(f"Unsupported unary operator: {type(node.op).__name__}")

    def visit_Name(self, node):
        if node.id != 'date' and not node.id.startswith('tag_'):
            raise QueryError(
                f"Unknown identifier '{node.id}'. "
                f"Tags must be prefixed with # and string values must be quoted."
            )
        if not self.negated and node.id.startswith('tag_'):
            self.positive_vars.add(node.id)
        self.generic_visit(node)


def tokenize(query: str) -> list[str]:
    """Split query into tokens: operators, parens, #tags, dates, and values."""
    pattern = r'"[^"]*"|\'[^\']*\'|[()]|[><=!]+|[^\s()><=!]+'
    return [m.group(0) for m in re.finditer(pattern, query)]

def is_value_end(token: str) -> bool:
    """True if token represents the end of a value/expression."""
    if not token: return False
    return token.startswith('#') or token.startswith(('"', "'")) or token == ')' or token[0].isdigit()

def is_value_start(token: str) -> bool:
    """True if token represents the start of a new value/expression."""
    if not token: return False
    t = token.lower()
    return t.startswith('#') or t in ('not', 'date', '(')


def parse(query: str):
    """
    Normalizes syntax, inserts implicit 'and', auto-quotes bare dates,
    translates #tags to safe Python variables, and statically analyzes the AST.
    """
    tokens = tokenize(query)
    norm = []

    for i, tok in enumerate(tokens):
        lower_tok = tok.lower()

        if lower_tok in ('and', 'or', 'not'):
            tok = lower_tok

        # Implicit 'and' insertion
        if i > 0 and is_value_end(norm[-1]) and is_value_start(tok):
            norm.append('and')

        # Auto-quote bare date values following a comparison operator
        if len(norm) >= 2 and norm[-2].lower() == 'date' and norm[-1] in ('==', '!=', '<', '<=', '>', '>='):
            if not tok.startswith(('"', "'")):
                tok = f'"{tok}"'

        norm.append(tok)

    tag_to_var = {}
    var_to_tag = {}
    final_tokens = []

    for tok in norm:
        if tok.startswith('#'):
            if tok not in tag_to_var:
                var_name = f"tag_{len(tag_to_var)}"
                tag_to_var[tok] = var_name
                var_to_tag[var_name] = tok
            final_tokens.append(tag_to_var[tok])
        else:
            final_tokens.append(tok)

    code_str = " ".join(final_tokens)

    try:
        tree = ast.parse(code_str, mode='eval')
    except SyntaxError as e:
        raise QueryError(f"Invalid query syntax — {e.msg}\nParsed as: {code_str}")

    validator = QueryValidator()
    validator.visit(tree)
    positive_tags = {var_to_tag[v] for v in validator.positive_vars}

    code = compile(tree, '<query>', 'eval')

    return code, tag_to_var, positive_tags


def baloo_query(tag: str) -> set[str]:
    """Fetch candidate absolute paths from Baloo index for a single tag."""
    tag_clean = tag.lstrip('#')
    try:
        r = subprocess.run(['baloosearch6', f'tags:{tag_clean}'],
                           capture_output=True, text=True)
        return {line.strip() for line in r.stdout.splitlines() if line.startswith('/')}
    except FileNotFoundError:
        raise QueryError("baloosearch6 not found. Is Baloo installed?")


def get_xattr(path: str, attr: str) -> str | None:
    """Safely read extended attribute."""
    try:
        return os.getxattr(path, attr).decode('utf-8')
    except OSError:
        return None


def main(query: str):
    try:
        code, tag_to_var, positive_tags = parse(query)

        if not positive_tags:
            raise QueryError("Query must contain at least one positive (non-negated) #tag.")

        # 1. Build Candidate Pool
        # We query Baloo strictly for positive tags to minimize disk I/O.
        # Negated tags are checked efficiently in-memory.
        candidates = set()
        for tag in positive_tags:
            candidates |= baloo_query(tag)

        if not candidates:
            return

        # 2. Per-File Evaluation
        safe_globals = {"__builtins__": {}}
        matches = []

        for path in candidates:
            raw_tags = get_xattr(path, 'user.xdg.tags')
            file_tags = {t.strip() for t in raw_tags.split(',')} if raw_tags else set()

            raw_date = get_xattr(path, 'user.dublincore.date')

            # Inject per-file evaluation environment
            locs = {'date': DateObj(raw_date) if raw_date else MissingDate()}
            for original_tag, var_name in tag_to_var.items():
                locs[var_name] = (original_tag.lstrip('#') in file_tags)

            try:
                if eval(code, safe_globals, locs):
                    matches.append(path)
            except (TypeError, ValueError):
                # Ignore type mismatches from unusual xattr values
                pass

        for match in sorted(matches):
            print(match)

    except QueryError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('query', nargs='?')
    parser.add_argument('-h', '--help', action='store_true')
    args = parser.parse_args()

    if args.help or not args.query:
        print(HELP_TEXT)
        sys.exit(0)

    main(args.query)
