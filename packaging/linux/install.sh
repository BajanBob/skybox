#!/bin/sh
# Installs Skybox Recon for the current user: ~/.local/bin + menu/desktop launcher.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin"; APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/512x512/apps"
mkdir -p "$BIN" "$APPS" "$ICONS"
install -m 755 "$HERE/SkyboxRecon" "$BIN/SkyboxRecon"
install -m 755 "$HERE/skybox-cli" "$BIN/skybox-cli"
install -m 644 "$HERE/skybox-recon.png" "$ICONS/skybox-recon.png"
sed "s|^Exec=.*|Exec=$BIN/SkyboxRecon|" "$HERE/skybox-recon.desktop" > "$APPS/skybox-recon.desktop"
DESKTOP="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
if [ -d "$DESKTOP" ]; then
  cp "$APPS/skybox-recon.desktop" "$DESKTOP/" && chmod +x "$DESKTOP/skybox-recon.desktop"
  gio set "$DESKTOP/skybox-recon.desktop" metadata::trusted true 2>/dev/null || true
fi
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" >/dev/null 2>&1 || true
echo "Installed. Start 'Skybox Recon' from your applications menu or desktop."
echo "For serial ports add yourself to the dialout (or uucp) group, then log out and in."
