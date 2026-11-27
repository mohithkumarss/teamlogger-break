#!/usr/bin/env bash
# Build dist/teamlogger-break_<version>_all.deb from the app sources.
# Usage: packaging/build-deb.sh [version]
set -euo pipefail
umask 022
VERSION="${1:-1.0.0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
PKG="$STAGE/teamlogger-break"

install -d "$PKG/DEBIAN" "$PKG/opt/teamlogger-break" "$PKG/usr/bin" "$PKG/usr/share/applications"
for f in teamlogger_break.py teamlogger_break_gui.py teamlogger_break_tray.py teamlogger_activity.py teamlogger_phone.py teamlogger_ui.py; do
  install -m 755 "$ROOT/$f" "$PKG/opt/teamlogger-break/$f"
done

install -d "$PKG/usr/share/icons/hicolor/scalable/apps"
install -m 644 "$ROOT/data/teamlogger-break.svg" "$PKG/usr/share/icons/hicolor/scalable/apps/teamlogger-break.svg"
install -d "$PKG/usr/share/teamlogger-break/fonts"
install -m 644 "$ROOT"/fonts/*.ttf "$ROOT/fonts/OFL.txt" "$ROOT/fonts/TRADEMARKS.md" "$PKG/usr/share/teamlogger-break/fonts/"

cat > "$PKG/usr/bin/teamlogger-break" <<'SH'
#!/bin/sh
exec /usr/bin/python3 /opt/teamlogger-break/teamlogger_break_gui.py "$@"
SH
chmod 755 "$PKG/usr/bin/teamlogger-break"

cat > "$PKG/usr/share/applications/teamlogger-break.desktop" <<'DT'
[Desktop Entry]
Type=Application
Name=TeamLogger Break
Comment=Take and resume TeamLogger breaks on a schedule
Exec=/usr/bin/python3 "/opt/teamlogger-break/teamlogger_break_gui.py"
Icon=teamlogger-break
Terminal=false
Categories=Utility;
StartupNotify=false
StartupWMClass=io.github.local.TeamLoggerBreak
DT

cat > "$PKG/DEBIAN/control" <<CTL
Package: teamlogger-break
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Maintainer: Local <noreply@localhost>
Depends: python3, python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, gir1.2-graphene-1.0, gir1.2-gtk-3.0, gir1.2-ayatanaappindicator3-0.1, libnotify-bin, procps
Recommends: teamlogger
Description: Scheduled breaks for the TeamLogger desktop client
 GTK app with a tray icon that takes and resumes TeamLogger breaks on a schedule.
CTL

cat > "$PKG/DEBIAN/postrm" <<'SH'
#!/bin/sh
set -e
if [ "$1" = "purge" ] || [ "$1" = "remove" ]; then
  rm -rf /opt/teamlogger-break/__pycache__
fi
SH
chmod 755 "$PKG/DEBIAN/postrm"

mkdir -p "$ROOT/dist"
OUT="$ROOT/dist/teamlogger-break_${VERSION}_all.deb"
dpkg-deb --root-owner-group --build "$PKG" "$OUT"
echo "Built $OUT"
