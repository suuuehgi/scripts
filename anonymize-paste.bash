#!/usr/bin/env bash
set -euo pipefail

# Get clipboard content
text=$(wl-paste 2>/dev/null) || { echo "Nothing copied" >&2; exit 1; }

# Anonymize
# (anonymize is a symlink to anonymize.py)
result=$(echo "$text" | ~/.local/bin/anonymize)

# Time to release the keyboard shortcut
# (if this script is being bound to a key combination)
sleep .3

# Alternative: ydotool key 29:1 47:1 47:0 29:0   # Ctrl+V
# (pasty is a symlink to paste.bash)
~/.local/bin/pasty "$result"
