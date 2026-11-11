#!/bin/sh
# Refresh the translation files after interface text changed, then compile them:
#   cornerplay/i18n/update.sh          (needs Qt's lupdate and lrelease: qt6-tools on Arch)
# Translate with Qt Linguist (linguist cornerplay/i18n/cornerplay_<lang>.ts) or any .ts editor.
# A new language: copy cornerplay_ro.ts to cornerplay_<lang>.ts, set language="<lang>" in it,
# translate, and add the language to LANGUAGES in cornerplay/config.py.
set -eu
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SRC=$(dirname "$DIR")
BIN=$(dirname "$(command -v lupdate 2>/dev/null || echo /usr/lib/qt6/bin/lupdate)")
[ -x "$BIN/lupdate" ] || BIN=/usr/lib/qt6/bin
for ts in "$DIR"/cornerplay_*.ts; do
    "$BIN/lupdate" -silent -no-obsolete "$SRC"/qml/*.qml "$SRC"/app.py -ts "$ts"
    "$BIN/lrelease" -silent -nounfinished "$ts" -qm "${ts%.ts}.qm"
done
echo "Updated: $(ls "$DIR"/*.qm | xargs -n1 basename | tr '\n' ' ')"
