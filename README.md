# AIO Launch

One library for Steam, Epic Games, GOG, Amazon Games and Battle.net on Linux.
PySide6 + QML; follows the Ryoku palette in `~/.cache/ryoku/colors.json`.

## Install

Download `aiolaunch.run` from the
[latest release](https://github.com/raulgbh-ctrl/aio-launch/releases/latest), then:

    sh aiolaunch.run

Or in one go:

    curl -fLO https://github.com/raulgbh-ctrl/aio-launch/releases/latest/download/aiolaunch.run && sh aiolaunch.run

One file, any Linux PC, no root needed for AIO Launch itself.

It installs into `~/.local`, adds AIO Launch to the app menu, and sets up what games need:
the Epic/GOG/Amazon backends and umu-launcher are downloaded into `~/.local/share/aiolaunch/bin`
(no root), and Steam comes from your package manager or Flathub (asks first). If the system has no PySide6 it sets up
a private Python environment instead (about 260 MB). From a copy of this folder,
`./install.sh` does the same; `./install.sh --dev` runs from the folder in place.

    sh ~/.local/lib/aiolaunch/install.sh --uninstall   # remove (keeps settings and games)
    sh ~/.local/lib/aiolaunch/install.sh --purge       # also remove settings and cache
    ./make-installer.sh                           # rebuild dist/aiolaunch-<version>.run

## Use

    aiolaunch                  # open the library
    aiolaunch --status         # what each store backend still needs
    aiolaunch --fetch-backends # download legendary, gogdl and nile into ~/.local/share/aiolaunch/bin
    aiolaunch --tv             # full screen TV mode (controller or arrow keys); F11 toggles it
    aiolaunch --demo           # sample library, nothing is launched

| Store      | Library from                         | Install / launch through            |
|------------|--------------------------------------|-------------------------------------|
| Steam      | local appmanifests (+ Web API key)   | the Steam client (`steam://` URLs)  |
| Epic       | `legendary list`                     | legendary + Proton (umu-run)        |
| GOG        | GOG web API                          | gogdl + Proton (umu-run)            |
| Amazon     | `nile library sync`                  | nile + Proton (umu-run)             |
| Battle.net | the Battle.net app's `product.db`    | Battle.net app under Proton         |

Needs: `steam`, `umu-launcher` (pacman), and the three CLIs above (or Heroic, whose
bundled copies are detected). Optional: `mangohud`, `gamemode`.

Files: settings `~/.config/aiolaunch`, logs and cover cache `~/.cache/aiolaunch`,
games and Proton prefixes `~/Games/aiolaunch` (changeable in Settings).
Code: `aiolaunch/stores/*.py` is one file per store; `aiolaunch/app.py` is the Qt glue; `aiolaunch/qml` the UI.

## Features

- **Merged duplicates**: a game owned on several stores is one tile; its panel asks which launcher to use and remembers it (Settings > Library to turn off).
- **DLC**: the DLC button on a game lists DLC for Steam (installed / available), Epic (owned) and GOG (owned / available).
- **Covers**: store art first, then SteamGridDB (API key in Settings > Library), then Steam's store matched by title. Per-game custom cover under Options.
- **Themes**: follow the Ryoku desktop palette, presets, or your own accent + background; cover size, corner radius, badges (Settings > Appearance).
- **Proton**: default version in Settings > Compatibility; per-game Proton, MangoHud, GameMode, env vars and launch arguments under a game's Options.
- **TV mode / controller** (`aiolaunch/gamepad.py`, SDL2): D-pad or stick = move, A = play, X = actions, Y = installed only, LB/RB = store, B = back, Start = toggle TV mode.

## Status and licence

Early software: the store sign-in, install and launch paths are built against the
legendary, gogdl and nile command lines but have had little real-world testing. AIO Launch is
not affiliated with Valve, Epic Games, GOG, Amazon or Blizzard. MIT licensed, see `LICENSE`.
