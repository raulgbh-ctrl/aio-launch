# Kura

One library for Steam, Epic Games, GOG, Amazon Games and Battle.net on Linux.
PySide6 + QML; follows the Ryoku palette in `~/.cache/ryoku/colors.json`.

## Install

Download `kura-0.1.0.run` from the
[latest release](https://github.com/raulgbh-ctrl/kura/releases/latest), then:

    sh kura-0.1.0.run

Or in one go:

    curl -fLO https://github.com/raulgbh-ctrl/kura/releases/latest/download/kura-0.1.0.run && sh kura-0.1.0.run

One file, any Linux PC, no root needed for Kura itself.

It installs into `~/.local`, adds Kura to the app menu, and offers to install Steam,
umu-launcher and the Epic/GOG/Amazon backends. If the system has no PySide6 it sets up
a private Python environment instead (about 260 MB). From a copy of this folder,
`./install.sh` does the same; `./install.sh --dev` runs from the folder in place.

    sh ~/.local/lib/kura/install.sh --uninstall   # remove (keeps settings and games)
    sh ~/.local/lib/kura/install.sh --purge       # also remove settings and cache
    ./make-installer.sh                           # rebuild dist/kura-<version>.run

## Use

    kura                  # open the library
    kura --status         # what each store backend still needs
    kura --fetch-backends # download legendary, gogdl and nile into ~/.local/share/kura/bin
    kura --tv             # full screen TV mode (controller or arrow keys); F11 toggles it
    kura --demo           # sample library, nothing is launched

| Store      | Library from                         | Install / launch through            |
|------------|--------------------------------------|-------------------------------------|
| Steam      | local appmanifests (+ Web API key)   | the Steam client (`steam://` URLs)  |
| Epic       | `legendary list`                     | legendary + Proton (umu-run)        |
| GOG        | GOG web API                          | gogdl + Proton (umu-run)            |
| Amazon     | `nile library sync`                  | nile + Proton (umu-run)             |
| Battle.net | the Battle.net app's `product.db`    | Battle.net app under Proton         |

Needs: `steam`, `umu-launcher` (pacman), and the three CLIs above (or Heroic, whose
bundled copies are detected). Optional: `mangohud`, `gamemode`.

Files: settings `~/.config/kura`, logs and cover cache `~/.cache/kura`,
games and Proton prefixes `~/Games/kura` (changeable in Settings).
Code: `kura/stores/*.py` is one file per store; `kura/app.py` is the Qt glue; `kura/qml` the UI.

## Features

- **Merged duplicates**: a game owned on several stores is one tile; its panel asks which launcher to use and remembers it (Settings > Library to turn off).
- **DLC**: the DLC button on a game lists DLC for Steam (installed / available), Epic (owned) and GOG (owned / available).
- **Covers**: store art first, then SteamGridDB (API key in Settings > Library), then Steam's store matched by title. Per-game custom cover under Options.
- **Themes**: follow the Ryoku desktop palette, presets, or your own accent + background; cover size, corner radius, badges (Settings > Appearance).
- **Proton**: default version in Settings > Compatibility; per-game Proton, MangoHud, GameMode, env vars and launch arguments under a game's Options.
- **TV mode / controller** (`kura/gamepad.py`, SDL2): D-pad or stick = move, A = play, X = actions, Y = installed only, LB/RB = store, B = back, Start = toggle TV mode.

## Status and licence

Early software: the store sign-in, install and launch paths are built against the
legendary, gogdl and nile command lines but have had little real-world testing. Kura is
not affiliated with Valve, Epic Games, GOG, Amazon or Blizzard. MIT licensed, see `LICENSE`.
