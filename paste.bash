#!/usr/bin/env bash
set -euo pipefail

# When launched from an AppImage, DBUS_SESSION_BUS_ADDRESS may not be set.
# Fall back to the predictable systemd socket path so qdbus-qt6 can reach KWin and Klipper.
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"

# AppImage bundles override LD_LIBRARY_PATH; unset it so system tools use system libraries
unset LD_LIBRARY_PATH

# Known terminal window classes (lowercase for matching)
TERMINALS="alacritty|konsole|xterm|kitty|foot|wezterm|gnome-terminal|tilix|terminator|yakuake|rxvt|urxvt|xfce4-terminal"

if [[ "${1-}" == "-h" || "${1-}" == "--help" ]]; then
cat << EOF
Usage: ${0##*/} <text>

A Wayland-native paste script.

Pastes <text> into the focused window.
Uses Ctrl+Shift+V for terminal emulators and Ctrl+V for GUI applications.

Notes:
- Requires: ydotool, wl-copy, qdbus-qt6, journalctl
- KDE Wayland only (uses KWin scripting to detect the active window class)
- ydotoold daemon must be running

Examples:
${0##*/} "Hello World"
${0##*/} "foo bar"
EOF
exit 0
fi

if [[ $# -lt 1 || -z "${1-}" ]]; then
    echo "Error: no text argument provided. Use -h for help." >&2
    exit 1
fi

text="$1"

# Check for the presence of the used commands
for cmd in qdbus-qt6 wl-copy ydotool journalctl; do
    command -v "$cmd" &>/dev/null || { echo "Error: missing required command: $cmd" >&2; exit 1; }
done

get_active_window_class() {
    local tmpscript marker script_id wclass
    tmpscript=$(mktemp /tmp/kwin_wclass_XXXX.js)
    marker="DOTOOL_WCLASS_$$"
    cat > "$tmpscript" << JSEOF
console.info("${marker}:" + workspace.activeWindow.resourceClass);
JSEOF

    script_id=$(qdbus-qt6 org.kde.KWin /Scripting org.kde.kwin.Scripting.loadScript "$tmpscript" "$marker" 2>/dev/null)

    # Bail out early if KWin refused to load the script
    if [[ -z "$script_id" ]]; then
        rm -f "$tmpscript"
        echo ""
        return
    fi

    qdbus-qt6 org.kde.KWin "/Scripting/Script${script_id}" org.kde.kwin.Script.run 2>/dev/null

    # KWin scripts output asynchronously to the journal; poll until result appears
    # (up to 10 × 20ms = 200ms max)
    wclass=""
    for _ in {1..10}; do
        sleep 0.02
        wclass=$(journalctl --user --since "2 seconds ago" --no-pager 2>/dev/null \
            | grep -F "$marker" | tail -1 | sed "s/.*${marker}://")
        [[ -n "$wclass" ]] && break
    done

    qdbus-qt6 org.kde.KWin "/Scripting/Script${script_id}" org.kde.kwin.Script.stop 2>/dev/null || true

    # Unregister from KWin — without this, each call leaks a script registration
    qdbus-qt6 org.kde.KWin /Scripting org.kde.kwin.Scripting.unloadScript "$marker" &>/dev/null || true

    rm -f "$tmpscript"
    echo "$wclass"
}

is_terminal() {
    local wclass
    wclass=$(get_active_window_class)
    [[ "${wclass,,}" =~ ($TERMINALS) ]]
}

terminal_mode=false
is_terminal && terminal_mode=true

# Save previous clipboard entry from Klipper history before overwriting
old_clipboard=$(qdbus-qt6 org.kde.klipper /klipper \
    org.kde.klipper.klipper.getClipboardHistoryItem 0 2>/dev/null || true)

# Copy transcribed text to clipboard
printf %s "$text" | wl-copy --type 'text/plain;charset=utf-8'

# wait until pasting to clipboard succeeded (max ~500ms)
for _ in {1..25}; do
    wl-paste --no-newline 2>/dev/null | grep -qF "$result" && break
    sleep 0.02
done

# Terminals require Ctrl+Shift+V; GUI apps use Ctrl+V
# Ctrl (29), Shift (42), V (47)
if $terminal_mode; then
    # Ctrl+Shift+V
    ydotool key 29:1 42:1 47:1 47:0 42:0 29:0
else
    # Ctrl+V
    ydotool key 29:1 47:1 47:0 29:0
fi

# Wait for the paste to complete before restoring the clipboard;
# restoring too early causes the old content to be pasted instead of the transcription.
sleep 0.3

# Restore the clipboard to its prior state
if [[ -n "$old_clipboard" ]]; then
    qdbus-qt6 org.kde.klipper /klipper org.kde.klipper.klipper.setClipboardContents "$old_clipboard" 2>/dev/null || true
else
    wl-copy --clear 2>/dev/null || true
fi
