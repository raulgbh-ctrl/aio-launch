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

- **Game updates**: Epic, GOG and Amazon games are checked for updates on every refresh. A game with one gets an ↑ badge and an Update button (TV mode: in its actions), and a toast says when a new update is found. Epic compares the installed version with legendary's latest build, GOG compares gogdl's installed build with GOG's newest public build, Amazon asks `nile list-updates`.
- **Playtime**: Epic, GOG and Amazon games are timed while they run (also when started from Steam through `--play`); Steam's own playtime is read from Steam. A game's panel shows hours played and when you last played. "Continue playing" above the library lists your most recent games, and the sort menu orders the library by name, recently played or most played. Battle.net games are not timed (its app stays open after a game closes). Stored in `~/.local/share/aiolaunch/playtime.json`.
- **Hide games**: Hide on a game's panel (or in TV mode's actions); hidden games live under "Hidden games" in the sidebar, where Unhide brings them back.
- **Games in Steam / Game Mode**: Settings > Library > Add games to Steam puts every installed Epic, GOG, Amazon and Battle.net game into Steam as a non-Steam game, with its cover, banner, background and logo (SteamGridDB if you added a key, otherwise Steam's store art, otherwise the store's own). Each runs through `aiolaunch --play`, so Proton settings and cloud saves still apply. "Keep installed games in Steam automatically" adds new installs and removes uninstalled or hidden games whenever Steam is closed. "Add AIO Launch" adds the app itself, opening in TV mode.
- **Merged duplicates**: a game owned on several stores is one tile; its panel asks which launcher to use and remembers it (Settings > Library to turn off).
- **DLC**: the DLC button on a game lists DLC for Steam (installed / available), Epic (owned) and GOG (owned / available).
- **Covers and banners**: store art first, then SteamGridDB (API key in Settings > Library), then Steam's store matched by title. Per-game custom cover under Options. Every game also gets backup covers and wide banner art, tried in order when one fails to load: Steam's own asset list for the matching Steam app (Epic, GOG and Amazon games are matched to Steam by title, once, and cached), Steam's local cache, Epic's 16:9 key art, GOG's Galaxy background, and SteamGridDB heroes when a key is set. Cached in `~/.cache/aiolaunch` (`steam_assets.json`, `cover_lookup.json`).
- **Look**: games show their own logo (Steam, Epic or GOG logo art, or the title when there is none); the banner, the game panel and TV mode take on the focused game's colour, picked from its cover (`gamecolour.py`, cached); covers shimmer while they load; tiles fade in; installs show a progress strip along the bottom of the cover.
- **Screenshots and trailers**: the game panel shows the game's screenshots (click one to see it full size; arrow keys to browse). In TV mode the focused game's art slowly pans, and after a couple of seconds its trailer plays muted behind the text (Settings > Appearance; needs Qt Multimedia, otherwise it is simply left out; never plays while a game has the focus). Optional soft navigation sounds in TV mode (off by default; synthesised, `aiolaunch/sounds/`).
- **Font**: [Inter](https://rsms.me/inter/) (SIL Open Font Licence, `aiolaunch/fonts/OFL.txt`) is bundled so the app looks the same on every desktop.
- **Button icons**: from [Lucide](https://lucide.dev) (ISC licence), in `aiolaunch/icons/ui/`.
- **Store logos**: from [Simple Icons](https://simpleicons.org) (CC0), in `aiolaunch/icons/`. The logos are trademarks of their owners and are only used to show which store a game belongs to.
- **Themes**: follow the Ryoku desktop palette, presets, or your own accent + background; cover size, corner radius, badges (Settings > Appearance).
- **Proton**: default version in Settings > Compatibility; per-game Proton, MangoHud, GameMode, env vars and launch arguments under a game's Options.
- **TV mode / controller** (`aiolaunch/gamepad.py`, SDL2): D-pad or stick = move, A = play, X = actions, Y = installed only, LB/RB = store, B = back, Start = toggle TV mode. The on-screen hints use the connected pad's own glyphs: Xbox (also the Steam Deck), PlayStation, or Nintendo (labelled by position).
- **ProtonDB**: each game matched to Steam shows its [ProtonDB](https://www.protondb.com) rating (Platinum, Gold, Silver, Bronze, Borked), from players' reports of how it runs on Linux: a badge on the cover (Settings > Appearance to hide it), a label in the game panel that opens the game's ProtonDB page (with the trending tier when it differs), and in TV mode. Fetched in the background after a refresh, cached for a week (`protondb.py`).
- **About each game**: description, genres, developer and release year in the game panel and in TV mode, from GOG for GOG games, from Steam's store for any game matched to Steam, or the store's own text (`details.py`, cached for a month).

## Status and licence

Early software: the store sign-in, install and launch paths are built against the
legendary, gogdl and nile command lines but have had little real-world testing. AIO Launch is
not affiliated with Valve, Epic Games, GOG, Amazon or Blizzard. MIT licensed, see `LICENSE`.
