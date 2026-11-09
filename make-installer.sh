#!/bin/sh
# Build dist/kura-<version>.run: one file you can copy to any Linux PC and run
# with `sh kura-<version>.run`. It unpacks itself to a temp folder and runs install.sh.
set -eu
SRC=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$SRC/kura/__init__.py")
OUT=$SRC/dist/kura-$VERSION.run
mkdir -p "$SRC/dist"

cat > "$OUT" <<'EOF'
#!/bin/sh
# Kura self-extracting installer. Usage: sh kura-X.Y.Z.run [install.sh options]
set -eu
TMP=$(mktemp -d "${TMPDIR:-/tmp}/kura-install.XXXXXX")
trap 'rm -rf "$TMP"' EXIT INT TERM
LINE=$(awk '/^__PAYLOAD__$/ { print NR + 1; exit }' "$0")
tail -n +"$LINE" "$0" | tar -xz -C "$TMP"
sh "$TMP/kura/install.sh" "$@"
exit $?
__PAYLOAD__
EOF
tar -cz -C "$SRC/.." --exclude='__pycache__' --exclude='dist' --exclude='.git' \
    --transform "s,^$(basename "$SRC"),kura," \
    "$(basename "$SRC")/kura" "$(basename "$SRC")/install.sh" "$(basename "$SRC")/README.md" >> "$OUT"
chmod +x "$OUT"
echo "Built $OUT ($(du -h "$OUT" | cut -f1))"
