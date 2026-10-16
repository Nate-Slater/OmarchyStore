#!/bin/sh
set -eu

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
APP_DIR="$DATA_HOME/omarchy-store"
BIN_DIR="$HOME/.local/bin"
APPLICATIONS_DIR="$DATA_HOME/applications"
LAUNCHER="$BIN_DIR/omarchy-store"
DESKTOP_FILE="$APPLICATIONS_DIR/org.omarchy.Store.desktop"

case "$DATA_HOME" in
  /*) ;;
  *) printf 'XDG_DATA_HOME must be an absolute path: %s\n' "$DATA_HOME" >&2; exit 1 ;;
esac

for target in "$APP_DIR" "$LAUNCHER" "$DESKTOP_FILE"; do
  if [ -e "$target" ] || [ -L "$target" ]; then
    printf 'Refusing to overwrite existing path: %s\n' "$target" >&2
    exit 1
  fi
done

install -d "$APP_DIR" "$BIN_DIR" "$APPLICATIONS_DIR"
install -m 0644 "$SOURCE_DIR/app.py" "$SOURCE_DIR/store_model.py" "$APP_DIR/"

cat > "$LAUNCHER" <<'EOF'
#!/bin/sh
set -eu
DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
exec python3 "$DATA_HOME/omarchy-store/app.py" "$@"
EOF
chmod 0755 "$LAUNCHER"
install -m 0644 "$SOURCE_DIR/org.omarchy.Store.desktop" "$DESKTOP_FILE"

printf 'Installed Omarchy Store. Launch with: %s\n' "$LAUNCHER"
