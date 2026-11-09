#!/bin/sh
# Build dist/aiolaunch-<version>.run: one file you can copy to any Linux PC and run
# with `sh aiolaunch-<version>.run`. It unpacks itself to a temp folder and runs install.sh.
set -eu
SRC=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$SRC/aiolaunch/__init__.py")
OUT=$SRC/dist/aiolaunch-$VERSION.run
mkdir -p "$SRC/dist"

cat > "$OUT" <<'EOF'
#!/bin/sh
# AIO Launch self-extracting installer. Usage: sh aiolaunch-X.Y.Z.run [install.sh options]
set -eu
TMP=$(mktemp -d "${TMPDIR:-/tmp}/aiolaunch-install.XXXXXX")
trap 'rm -rf "$TMP"' EXIT INT TERM
LINE=$(awk '/^__PAYLOAD__$/ { print NR + 1; exit }' "$0")
tail -n +"$LINE" "$0" | tar -xz -C "$TMP"
sh "$TMP/aiolaunch/install.sh" "$@"
exit $?
__PAYLOAD__
EOF
tar -cz -C "$SRC/.." --exclude='__pycache__' --exclude='dist' --exclude='.git' \
    --transform "s,^$(basename "$SRC"),aiolaunch," \
    "$(basename "$SRC")/aiolaunch" "$(basename "$SRC")/install.sh" "$(basename "$SRC")/README.md" >> "$OUT"
chmod +x "$OUT"
cp "$OUT" "$SRC/dist/aiolaunch.run"   # stable name, so the "latest release" link never changes
echo "Built $OUT ($(du -h "$OUT" | cut -f1))"
