#!/usr/bin/env bash
set -euo pipefail

# PRIMARY selection = whatever is currently highlighted (no Ctrl+C needed)
text=$(wl-paste --primary 2>/dev/null) || { echo "Nothing selected" >&2; exit 1; }

# Transform
result=$(python3 ~/.local/bin/headlinify "$text")

# Time to release keys
# (If this script is being bound to a key combination - otherwise they mix up with the key presses emulated in the next line.)
sleep .3

# Alternative: ydotool key 29:1 47:1 47:0 29:0   # Ctrl+V
# (pasty is a symlink to anonymize.py)
~/.local/bin/pasty "$result"
