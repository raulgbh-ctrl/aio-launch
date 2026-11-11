#!/bin/sh
# Write the Flathub manifest for a release tag: the local manifest, with Cornerplay's own
# source taken from that git tag (Flathub builds from pinned sources, never a local folder).
#   packaging/flathub/make-manifest.sh v0.9.0   ->   packaging/flathub/io.github.raulgbh_ctrl.Cornerplay.yml
# Run it after the tag exists (pushed to GitHub), then copy the file into the Flathub repo.
set -eu
TAG=${1:?usage: make-manifest.sh <tag, e.g. v0.9.0>}
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
ID=io.github.raulgbh_ctrl.Cornerplay
COMMIT=$(git -C "$ROOT" rev-list -n 1 "$TAG")
python3 - "$ROOT/packaging/flatpak/$ID.yml" "$ROOT/packaging/flathub/$ID.yml" "$TAG" "$COMMIT" <<'PY'
import sys
src, out, tag, commit = sys.argv[1:5]
text = open(src).read()
old = """      - type: dir
        path: ../..
        skip:
          - .git
          - .flatpak-builder
          - dist
          - docs
          - tests
          - .ruff_cache
          - .pytest_cache
"""
assert old in text, "the cornerplay module's source changed: update make-manifest.sh"
new = f"""      - type: git
        url: https://github.com/raulgbh-ctrl/cornerplay.git
        tag: {tag}
        commit: {commit}
"""
text = text.replace(old, new).replace("# Cornerplay as a Flatpak. Build and install it from the repository's root:",
                                      "# Cornerplay on Flathub (made by packaging/flathub/make-manifest.sh from packaging/flatpak).\n#")
open(out, "w").write(text)
print(f"Wrote {out} for {tag} ({commit[:12]})")
PY
