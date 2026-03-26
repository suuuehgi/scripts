#!/usr/bin/env bash
set -euo pipefail

# PRIMARY selection = whatever is currently highlighted (no Ctrl+C needed)
text=$(wl-paste 2>/dev/null) || { echo "Nothing copied" >&2; exit 1; }

# Transform
# (anonymize is a symlink to anonymize.py)
result=$(echo "$text" | ~/.local/bin/anonymize)

# Write to clipboard and paste
printf %s "$result" | wl-copy --type 'text/plain;charset=utf-8'

# Alternative: ydotool key 29:1 47:1 47:0 29:0   # Ctrl+V
# (pasty is a symlink to paste.bash)
~/.local/bin/pasty "$result"
