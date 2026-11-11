#!/bin/sh
# Cornerplay inside the Flatpak.
export PYTHONPATH="/app/lib/cornerplay${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m cornerplay "$@"
