# Submitting Cornerplay to Flathub

Everything Flathub checks is already in place: the manifest builds, `flatpak-builder-lint`
passes the manifest and the AppStream file (two warnings: a newer KDE runtime exists, and the
host access explained below), the app id follows the GitHub rule
(`io.github.raulgbh_ctrl.Cornerplay`), and the metainfo has screenshots, an OARS rating and
release notes.

## Steps

1. Tag and push a release (for example `v0.9.0`), with `cornerplay.flatpak` attached.
2. `packaging/flathub/make-manifest.sh v0.9.0` writes the Flathub manifest, pinned to that tag.
3. Check it builds from the tag:
   `flatpak run org.flatpak.Builder --user --force-clean --install-deps-from=flathub build packaging/flathub/io.github.raulgbh_ctrl.Cornerplay.yml`
4. Fork https://github.com/flathub/flathub, branch from `new-pr`, add the manifest (and
   nothing else), and open a pull request against `new-pr` titled
   "Add io.github.raulgbh_ctrl.Cornerplay". Paste the text below into it.
5. Reviewers may ask for changes; once merged, Flathub makes a repository
   `flathub/io.github.raulgbh_ctrl.Cornerplay`: later releases are pull requests there
   (run step 2 for the new tag).

## Text for the pull request: why the app needs these permissions

Cornerplay is a game library and launcher (like Heroic, Lutris and Bottles) for Steam, Epic,
GOG, Amazon, Battle.net and itch.io games.

- `--talk-name=org.freedesktop.Flatpak`: Steam is a program on the host (or Flathub's Steam).
  Cornerplay starts it to install and launch Steam games (`steam://` URLs), and closes and
  reopens it around changes to Steam's own settings (a game's Proton version, non-Steam
  shortcuts for Game Mode). It also starts RetroArch on the host for retro games. Only those
  commands are run on the host (`cornerplay/host.py`).
- `--filesystem=~/.local/share/Steam`, `~/.steam`, `~/.var/app/com.valvesoftware.Steam`:
  Steam's library, artwork cache, Proton builds and `shortcuts.vdf`.
- `--filesystem=~/Games:create`: where games install. `--filesystem=xdg-data/umu:create`:
  umu-launcher's Steam Linux Runtime, shared with umu on the host (as umu asks Flatpak apps to).
- `--device=all`, `--allow=multiarch`, `--allow=devel`, `--allow=per-app-dev-shm`: controllers,
  the GPU, and 32-bit Windows games through Proton in the Steam Linux Runtime (sub-sandboxed
  with Flatpak's own mechanism; tested).
- Read-only: Heroic's and Lutris's folders (Proton builds and installed games to import),
  MangoHud's settings, RetroArch's cores; and Discord's local socket for Rich Presence (opt-in).
