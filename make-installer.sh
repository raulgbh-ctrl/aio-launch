#!/bin/sh
# Build dist/cornerplay-<version>.run: one file you can copy to any Linux PC and run
# with `sh cornerplay-<version>.run`. It unpacks itself to a temp folder and runs install.sh.
set -eu
SRC=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$SRC/cornerplay/__init__.py")
OUT=$SRC/dist/cornerplay-$VERSION.run
mkdir -p "$SRC/dist"

cat > "$OUT" <<'EOF'
#!/bin/sh
# Cornerplay self-extracting installer. Usage: sh cornerplay-X.Y.Z.run [install.sh options]
set -eu
TMP=$(mktemp -d "${TMPDIR:-/tmp}/cornerplay-install.XXXXXX")
trap 'rm -rf "$TMP"' EXIT INT TERM
LINE=$(awk '/^__PAYLOAD__$/ { print NR + 1; exit }' "$0")
tail -n +"$LINE" "$0" | tar -xz -C "$TMP"
sh "$TMP/cornerplay/install.sh" "$@"
exit $?
__PAYLOAD__
EOF
tar -cz -C "$SRC/.." --exclude='__pycache__' --exclude='dist' --exclude='.git' --exclude='docs' --exclude='packaging' \
    --transform "s,^$(basename "$SRC"),cornerplay," \
    "$(basename "$SRC")/cornerplay" "$(basename "$SRC")/install.sh" "$(basename "$SRC")/README.md" >> "$OUT"
chmod +x "$OUT"
cp "$OUT" "$SRC/dist/cornerplay.run"   # stable name, so the "latest release" link never changes
echo "Built $OUT ($(du -h "$OUT" | cut -f1))"
