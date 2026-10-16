#!/bin/sh
set -eu

DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
APP_DIR="$DATA_HOME/omarchy-store"
LAUNCHER="$HOME/.local/bin/omarchy-store"
DESKTOP_FILE="$DATA_HOME/applications/org.omarchy.Store.desktop"

if [ -L "$APP_DIR" ]; then
  printf 'Refusing to remove a symlinked application directory: %s\n' "$APP_DIR" >&2
  exit 1
fi

rm -f -- "$LAUNCHER" "$DESKTOP_FILE"
rm -f -- "$APP_DIR/app.py" "$APP_DIR/store_model.py"
if [ -d "$APP_DIR" ]; then
  rmdir -- "$APP_DIR" 2>/dev/null || {
    printf 'Left non-empty application data directory untouched: %s\n' "$APP_DIR" >&2
    exit 1
  }
fi

printf 'Removed Omarchy Store. No plugin data is managed by this app.\n'
