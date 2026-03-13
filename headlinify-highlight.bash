#!/usr/bin/env bash
set -euo pipefail

# PRIMARY selection = whatever is currently highlighted (no Ctrl+C needed)
text=$(wl-paste --primary 2>/dev/null) || { echo "Nothing selected" >&2; exit 1; }

# Transform
result=$(python3 ~/.local/bin/headlinify "$text")

# Write to clipboard and paste
printf %s "$result" | wl-copy --type 'text/plain;charset=utf-8'

# wait until pasting to clipboard succeeded (max ~500ms)
for _ in {1..25}; do
    wl-paste --no-newline 2>/dev/null | grep -qF "$result" && break
    sleep 0.02
done

# Alternative: ydotool key 29:1 47:1 47:0 29:0   # Ctrl+V
# (pasty is a symlink to anonymize.py)
~/.local/bin/pasty "$result"
