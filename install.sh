#!/bin/bash
# install.sh — Install RetroMIDI and register it with GNOME
set -e

echo "=== RetroMIDI Installer ==="
echo

# Check for system dependencies
echo "Checking system dependencies..."

MISSING=()
python3 -c "import gi" 2>/dev/null || MISSING+=("python3-gi")
dpkg -l gir1.2-gtk-3.0 &>/dev/null || MISSING+=("gir1.2-gtk-3.0")
command -v aplaymidi &>/dev/null || MISSING+=("alsa-utils")

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "Installing missing packages: ${MISSING[*]}"
    sudo apt-get install -y "${MISSING[@]}"
else
    echo "All system dependencies present."
fi

echo
echo "Installing RetroMIDI via pip..."
pip install --break-system-packages --editable .

echo
echo "Installing desktop entry..."
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
cp retromidi.desktop "$DESKTOP_DIR/retromidi.desktop"
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

echo
echo "Done! Run with:  retromidi"
echo "Or find 'RetroMIDI' in your GNOME application launcher."
