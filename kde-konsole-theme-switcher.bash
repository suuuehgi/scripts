#!/usr/bin/env bash
#
# Switches active KDE Konsole sessions between Dark and Light profile
# while setting this profile as the new default.
#
# Requires: Two set up Konsole profiles "Dark" and "Light"

apply_profile() {
    local PROFILE=$1
    
    # 1. Update config for newly opened terminals
    sed -i -E "s/DefaultProfile=.*/DefaultProfile=$PROFILE.profile/" ~/.config/konsolerc

    # 2. Update all running tabs and windows via D-Bus
    for instance in $(qdbus-qt6 | grep org.kde.konsole); do
        for session in $(qdbus-qt6 "$instance" | grep -oP '^/Sessions/\d+'); do
            qdbus-qt6 "$instance" "$session" org.kde.konsole.Session.setProfile "$PROFILE" >/dev/null 2>&1
        done
    done
}

sync_theme() {
    # Check the currently active global color scheme directly
    CURRENT_SCHEME=$(kreadconfig6 --group "General" --key "ColorScheme")
    
    if [[ "$CURRENT_SCHEME" == *"Dark"* ]]; then
        apply_profile "Dark"
    else
        apply_profile "Light"
    fi
}

# Initial sync
sync_theme

# Continuously listen for Plasma global configuration changes
dbus-monitor --session "type='signal',interface='org.kde.kconfig.notify',member='ConfigChanged'" | while read -r line; do
    if [[ "$line" == *"kdeglobals"* ]]; then
        
        # Debounce: Consume any further lines arriving within 1 second.
        # Once 1 second passes with no new output, the inner loop breaks.
        while read -t 1 -r _ignore; do
            :
        done
        
        # Run once after the config events settle
        sync_theme
    fi
done
