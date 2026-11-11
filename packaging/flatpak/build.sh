#!/bin/sh
# Build the Flatpak and install it for this user. --bundle also writes dist/cornerplay.flatpak.
# Needs: flatpak install flathub org.flatpak.Builder
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
ID=io.github.raulgbh_ctrl.Cornerplay
cd "$ROOT"
flatpak run org.flatpak.Builder --user --install-deps-from=flathub --force-clean --install \
    --repo=.flatpak-builder/repo --state-dir=.flatpak-builder \
    .flatpak-builder/build "packaging/flatpak/$ID.yml"
if [ "${1:-}" = "--bundle" ]; then
    mkdir -p dist
    flatpak build-bundle --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo \
        .flatpak-builder/repo dist/cornerplay.flatpak "$ID"
    echo "Built dist/cornerplay.flatpak ($(du -h dist/cornerplay.flatpak | cut -f1))"
fi
