#!/usr/bin/env bash
set -euo pipefail

# When launched from an AppImage, DBUS_SESSION_BUS_ADDRESS may not be set.
# Fall back to the predictable systemd socket path so qdbus-qt6 can reach KWin and Klipper.
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"

# AppImages sometimes bundle override LD_LIBRARY_PATH; unset it so system tools use system libraries
# (In case the script is being executed by an AppImage.)
unset LD_LIBRARY_PATH

# Known terminal window classes (lowercase for matching)
# Add yours: C. f. output of `kdotool getactivewindow getwindowclassname`
TERMINALS="alacritty|konsole|xterm|terminator|rxvt|terminal"

if [[ "${1-}" == "-h" || "${1-}" == "--help" ]]; then
    cat << EOF
Usage: ${0##*/} <text>

A Wayland-native paste script.

Pastes <text> into the focused window.
Uses Ctrl+Shift+V for terminal emulators and Ctrl+V for GUI applications.

Notes:
- Requires: qdbus-qt6, wl-copy, wl-paste, ydotool, kdotool and kdialog
- ydotoold daemon must be running

Examples:
${0##*/} "Hello World"
${0##*/} "foo bar"
EOF
    exit 0
fi

if [[ $# -lt 1 || -z "${1-}" ]]; then
    echo "Error: no text argument provided. Use -h/--help for help." >&2
    exit 1
fi

text="$1"

# Used instead of stderr because this script is typically invoked in the background.
notify_error() {
    kdialog --title "${0##*/}" --passivepopup "Paste failed: $1" 3
}

# Check for the presence of the used commands
for cmd in qdbus-qt6 wl-copy wl-paste ydotool kdotool kdialog; do
    # command -v "$cmd" &>/dev/null || { echo "Error: missing required command: $cmd" >&2; exit 1; }
    command -v "$cmd" &>/dev/null || { notify_error "Error: missing required command: $cmd"; exit 1; }
done

get_active_window_class() {
    local wclass
    wclass=$(kdotool getactivewindow getwindowclassname 2>/dev/null)

    if [[ -z "$wclass" ]]; then
        notify_error "Could not detect active window class via kdotool."
        exit 1
    fi

    echo "$wclass"
}

is_terminal() {
    local wclass
    wclass=$(get_active_window_class)
    [[ "${wclass,,}" =~ ($TERMINALS) ]]
}

terminal_mode=false
is_terminal && terminal_mode=true

# Save the current clipboard content from Klipper so it can be restored after pasting.
old_clipboard=$(qdbus-qt6 org.kde.klipper /klipper \
    org.kde.klipper.klipper.getClipboardHistoryItem 0 2>/dev/null || true)

# Write the text to the Wayland clipboard
printf %s "$text" | wl-copy --type 'text/plain;charset=utf-8'

# Wait for the Wayland compositor to recognize the new clipboard content (max 500ms).
# wl-copy forks to the background, so this loop verifies it is actually available.
clipboard_ok=false
for _ in {1..25}; do
    if wl-paste --no-newline 2>/dev/null | grep -qF -- "$text"; then
        clipboard_ok=true
        break
    fi
    sleep 0.02
done

if ! $clipboard_ok; then
    notify_error "Clipboard content was not confirmed after 500 ms — aborting."
    exit 1
fi

# Send the paste keystroke to the focused window.
# Terminals require Ctrl+Shift+V; GUI apps use Ctrl+V
# ydotool key codes: Ctrl=29, Shift=42, V=47. Suffix :1 = key-down, :0 = key-up.
if $terminal_mode; then
    # Ctrl+Shift+V
    ydotool key 29:1 42:1 47:1 47:0 42:0 29:0
else
    # Ctrl+V
    ydotool key 29:1 47:1 47:0 29:0
fi

# Wait for the target application to consume the paste before restoring the
# clipboard. Restoring too early causes the old content to be pasted instead
# of the intended text. There is no lightweight event to hook here.
sleep 0.3

# Restore the clipboard to its state before this script ran.
if [[ -n "$old_clipboard" ]]; then
    qdbus-qt6 org.kde.klipper /klipper org.kde.klipper.klipper.setClipboardContents "$old_clipboard" 2>/dev/null || true
else
    wl-copy --clear 2>/dev/null || true
fi
