#!/usr/bin/env bash
set -euo pipefail

# Get clipboard content
text=$(wl-paste 2>/dev/null) || { echo "Nothing copied" >&2; exit 1; }

# Anonymize
# (anonymize is a symlink to anonymize.py)
result="$(echo "$text" | ~/.local/bin/anonymize -d url)"

# Enclose in ``` (markdown code formatters)
result=$(printf '```\n%s\n```' "$result")

# Time to release keys
# (If this script is being bound to a key combination - otherwise they mix up with the key presses emulated in the next line.)
sleep .3

# Alternative: ydotool key 29:1 47:1 47:0 29:0   # Ctrl+V
# (pasty is a symlink to paste.bash)
~/.local/bin/pasty "$result"
