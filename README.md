<p align="center"><img src="docs/banner.jpg" alt="Cornerplay: your games, in one cozy place"></p>

# Cornerplay

**Your cosy corner for every game you own.**

Pull up a chair. Cornerplay gathers your Steam, Epic Games, GOG, Amazon Games and
Battle.net libraries into one warm, quiet place on Linux, so the game you want is always
right there: covers that keep up with the stores, the one you played last waiting up
front, a couch-friendly TV mode for the controller, and Proton sorted out behind the
scenes. No more hopping between five launchers to find something to play tonight.

*Formerly AIO Launch (and before that, Kura): your settings, sign-ins and games come along
by themselves, and the old `aiolaunch` command keeps working.*

PySide6 + QML; follows your desktop wallpaper's colours (the Ryoku palette in
`~/.cache/ryoku/colors.json`, or the wallpaper itself elsewhere).

## Install

Download `cornerplay.run` from the
[latest release](https://github.com/raulgbh-ctrl/cornerplay/releases/latest), then:

    sh cornerplay.run

Or in one go:

    curl -fLO https://github.com/raulgbh-ctrl/cornerplay/releases/latest/download/cornerplay.run && sh cornerplay.run

One file, any Linux PC, no root needed for Cornerplay itself.

It installs into `~/.local`, adds Cornerplay to the app menu, and sets up what games need:
the Epic/GOG/Amazon backends and umu-launcher are downloaded into `~/.local/share/cornerplay/bin`
(no root), and Steam comes from your package manager or Flathub (asks first). If the system has no PySide6 it sets up
a private Python environment instead (about 260 MB). From a copy of this folder,
`./install.sh` does the same; `./install.sh --dev` runs from the folder in place.

    sh ~/.local/lib/cornerplay/install.sh --uninstall   # remove (keeps settings and games)
    sh ~/.local/lib/cornerplay/install.sh --purge       # also remove settings and cache
    ./make-installer.sh                           # rebuild dist/cornerplay-<version>.run

## Use

    cornerplay                  # open the library
    cornerplay --status         # what each store backend still needs
    cornerplay --fetch-backends # download legendary, gogdl and nile into ~/.local/share/cornerplay/bin
    cornerplay --tv             # full screen TV mode (controller or arrow keys); F11 toggles it
    cornerplay --demo           # sample library, nothing is launched

| Store      | Library from                         | Install / launch through            |
|------------|--------------------------------------|-------------------------------------|
| Steam      | the Library tab's games, from Steam's own cache `appinfo.vdf` (or every owned game with a Web API key) | the Steam client (`steam://` URLs)  |
| Epic       | `legendary list`                     | legendary + Proton (umu-run)        |
| GOG        | GOG web API                          | gogdl + Proton (umu-run)            |
| Amazon     | `nile library sync`                  | nile + Proton (umu-run)             |
| Battle.net | the Battle.net app's `product.db`    | Battle.net app under Proton         |

Needs: `steam`, `umu-launcher` (pacman), and the three CLIs above (or Heroic, whose
bundled copies are detected). Optional: `mangohud`, `gamemode`.

Files: settings `~/.config/cornerplay`, logs and cover cache `~/.cache/cornerplay`,
games and Proton prefixes `~/Games/cornerplay` (changeable in Settings).
Code: `cornerplay/stores/*.py` is one file per store; `cornerplay/app.py` is the Qt glue; `cornerplay/qml` the UI.

## Features

- **Game updates**: Epic, GOG and Amazon games are checked for updates on every refresh. A game with one gets an ↑ badge and an Update button (TV mode: in its actions), and a toast says when a new update is found. Epic compares the installed version with legendary's latest build, GOG compares gogdl's installed build with GOG's newest public build, Amazon asks `nile list-updates`.
- **Playtime**: Epic, GOG and Amazon games are timed while they run (also when started from Steam through `--play`); Steam's own playtime is read from Steam. A game's panel shows hours played and when you last played. "Continue playing" above the library lists your most recent games, and the sort menu orders the library by name, recently played or most played. Battle.net games are not timed (its app stays open after a game closes). Stored in `~/.local/share/cornerplay/playtime.json`.
- **Games hidden in Steam** stay hidden: they go under "Hidden games" (read from Steam's synced collections), and the Steam view leaves them out; a game also owned on another store still shows through that copy. Unhide in Cornerplay to show one anyway (Steam is not changed).
- **Hide games**: Hide on a game's panel (or in TV mode's actions); hidden games live under "Hidden games" in the sidebar, where Unhide brings them back.
- **Games in Steam / Game Mode**: Settings > Library > Add games to Steam puts every installed Epic, GOG, Amazon and Battle.net game into Steam as a non-Steam game, with its cover, banner, background and logo (SteamGridDB if you added a key, otherwise Steam's store art, otherwise the store's own). Each runs through `cornerplay --play`, so Proton settings and cloud saves still apply. "Keep installed games in Steam automatically" adds new installs and removes uninstalled or hidden games whenever Steam is closed. "Add Cornerplay" adds the app itself, opening in TV mode.
- **Merged duplicates**: a game owned on several stores is one tile; its panel asks which launcher to use and remembers it (Settings > Library to turn off).
- **DLC**: the DLC button on a game (with the count once known) lists its DLC with art, whether it is installed or owned, and the price of what you do not own (in your currency). Owned DLC installs from there with progress, one at a time or all at once: Epic through legendary, GOG through gogdl. Steam installs owned DLC by itself and only says which is installed, so the others open in the Steam client to buy or install. Epic lists only the DLC you own.
- **Current covers**: for every game matched to Steam (on any store), Steam's current library capsule comes first; its URL changes whenever the art does (Warframe's new art, seasonal covers), so new art replaces the cached image. Steam's art is checked every 2 days, GOG's every week, Epic's game data every week; covers found by title are looked up again after two weeks. Settings > Library > Refresh artwork now does it at once.
- **Covers and banners**: store art first, then SteamGridDB (API key in Settings > Library), then Steam's store matched by title, then IGDB box art through Lutris's game list (for games Steam does not sell, such as World of Warcraft). Per-game custom cover under Options. Every game also gets backup covers and wide banner art, tried in order when one fails to load: Steam's own asset list for the matching Steam app (Epic, GOG and Amazon games are matched to Steam by title, once, and cached), Steam's local cache, Epic's 16:9 key art, GOG's Galaxy background, and SteamGridDB heroes when a key is set. Cached in `~/.cache/cornerplay` (`steam_assets.json`, `cover_lookup.json`).
- **Look**: games show their own logo (Steam, Epic or GOG logo art, or the title when there is none); the banner, the game panel and TV mode take on the focused game's colour, picked from its cover (`gamecolour.py`, cached); covers shimmer while they load; tiles fade in; installs show a progress strip along the bottom of the cover.
- **Screenshots and trailers**: the game panel shows the game's screenshots (click one to see it full size; arrow keys to browse). In TV mode the focused game's art slowly pans, and after a couple of seconds its trailer plays muted behind the text (Settings > Appearance; needs Qt Multimedia, otherwise it is simply left out; never plays while a game has the focus). Optional soft navigation sounds in TV mode (off by default; synthesised, `cornerplay/sounds/`).
- **Fonts**: [Nunito](https://github.com/googlefonts/nunito), rounded like the logo, for the interface (fixed weights made from the variable font), with [Inter](https://rsms.me/inter/) as the fallback, all SIL Open Font Licence (`cornerplay/fonts/OFL-Nunito.txt`, `OFL.txt`, `OFL-Outfit.txt`), bundled so the app looks the same on every desktop.
- **The look**: the C-and-play-button icon, and a logo that takes its colours from your theme (your wallpaper's colours; `cornerplay/art/brand/`), warm amber as the signature colour (the default "Cornerplay" theme; Follow wallpaper and the other presets are still in Settings > Appearance), store logos on coloured tiles, little scenes for empty screens (drawn in the theme's colours, `qml/EmptyScene.qml`), frosted pop-ups and notifications, a launch card when a game starts (its cover lifts and glows while it gets ready), a short splash while the library loads, and in TV mode a shelf reflection under the covers and an optional start-up animation with a chime. Cover shadows: none, soft or deep. With Follow wallpaper the wallpaper itself sits blurred behind the window, like frosted glass (Settings > Appearance; no compositor blur needed). Covers tilt toward the pointer with a soft light following it; a cover flies into the game page when opened and back when closed; pointing at a cover for a moment plays its trailer inside it (Settings > Appearance); Steam covers show a thin bar of achievements earned (gold when complete); in the evening the surfaces turn a little warmer (Settings > Appearance); store and shelf changes slide in. Downloads show their speed and time left (game page, TV mode, Quick Access), and a desktop notification says when one finishes while Cornerplay is in the background. and the logo animates in on the splash and the TV intro (the C swings round, the play button pops, the sparks flick on).
- **Button icons**: from [Lucide](https://lucide.dev) (ISC licence), in `cornerplay/icons/ui/`.
- **Store and ProtonDB logos**: from [Simple Icons](https://simpleicons.org) (CC0), in `cornerplay/icons/`. The logos are trademarks of their owners and are only used to show which store a game belongs to.
- **Themes**: follow the Ryoku desktop palette, presets, or your own accent + background; cover size, corner radius, badges (Settings > Appearance).
- **Proton**: every Proton build on the PC is offered, wherever it was installed: Valve's builds in any Steam library, Steam's compatibilitytools.d (ProtonUp-Qt, ProtonPlus, Cornerplay's GE-Proton download; also Flatpak and Snap Steam), Heroic, Lutris, umu, system packages and `STEAM_EXTRA_COMPAT_TOOLS_PATHS` (`protons.py`). Default version in Settings > Compatibility; per-game Proton, MangoHud, GameMode, env vars and launch arguments under a game's Options.
- **Proton for Steam games**: a Steam game's Options sets Steam's own per-game compatibility tool (Properties > Compatibility): Valve's builds (Steam downloads them when needed) and every other build on the PC; one that lives outside Steam (Heroic, Lutris, ...) is linked into Steam's compatibilitytools.d when chosen. Steam is closed and reopened around the change, and `config.vdf` is backed up first (`steamcompat.py`).
- **TV mode / controller** (`cornerplay/gamepad.py`, SDL2), laid out like SteamOS Game Mode: D-pad or stick = move (held, it speeds up), up/down = shelf, LT/RT = jump a screen, A = play, Start/Menu (or X) = the game's options, Guide (Xbox / PS / Home button) = the main menu sliding in from the left (Home, Search, Installed only, Next store, Exit TV mode, Quit), Guide + A or Share = quick access from the right (now playing with Quit, downloads with progress, sound / trailer / animated-art switches), Y = installed only, LB/RB = store, View/Select = search (an on-screen keyboard with numbers on top, QWERTY letters, a dash and an apostrophe, and a wide space bar; X deletes, Y types a space, View/Select is done), B = back (clears a search, then returns to the top shelf, then opens the main menu). Keyboard: F10 main menu, F9 quick access, F2 options, F11 leaves TV mode; Guide (F10) in the desktop window opens TV mode. Keyboard: arrows, Shift+arrows, Home/End, and just type to search. Shelves: Continue playing, Favourites, your collections, Recently added, Library. A clock and the battery level (Steam Deck, laptops) sit top right. The on-screen hints use the connected pad's own glyphs: Xbox (also the Steam Deck), PlayStation, or Nintendo (labelled by position).
- **Favourites and collections**: star a game (its panel, or TV mode's actions) and make your own collections ("Co-op nights", "Backlog"); they sit in the sidebar under the stores and are shelves in TV mode. Kept per game in `~/.config/cornerplay/games.json`.
- **Backlog, ratings and notes**: mark a game Playing, Want to play, Finished or Dropped, give it 1-5 stars and a note ("stuck on boss 3") in its panel. Statuses show in the sidebar and as TV shelves; sort the library by your rating.
- **Stats**: sidebar > Stats: hours played in total and per store, games played vs never started, your most played, and the last two weeks (Cornerplay logs each play session from 0.4.0 on; Steam only shares totals).
- **Storage**: sidebar > Storage: every installed game by size, how full each drive is, Free up space (games over 2 GB not played for three months), Uninstall, and Move to another folder or drive (Epic, GOG and Amazon, with progress; Steam games move in Steam's Settings > Storage; Battle.net in its app).
- **Performance profiles**: Battery saver (30 fps), Balanced (60 fps), both with FSR upscaling, or Max quality; an FPS counter (MangoHud). Default in Settings > Compatibility, per game under Options (Epic, GOG, Amazon). Each game keeps its own shader cache (`~/.cache/cornerplay/shaders`) so only the first run stutters.
- **Fix it** (a game's Options): Repair files (Epic, GOG, Amazon), Reset Proton prefix (the old one is renamed, not deleted), Open log.
- **Controller support**: from Steam's store data, in the game panel and TV mode; Steam games that are not fully supported link to Steam's controller layout.
- **What should I play?** (sidebar): a pick from your backlog, by how long you have; never finished or dropped games.
- **Now playing**: a bar (and a TV chip) while a game started from Cornerplay runs, with Quit and Force close.
- **People**: Settings > People & sync: each person has their own favourites, collections, statuses, stars, notes and stats; switch at the top of the sidebar.
- **Sync between PCs**: pick a folder Syncthing / Nextcloud / Dropbox already syncs; personal data merges game by game and playtime adds up across PCs.
- **Health check** (sidebar): Vulkan, Proton runner and versions, store tools, Steam, sign-ins, disk space, the sign-in window and controller support, each with a fix (a download, a sign-in, or the exact command to copy). The sidebar shows "!" when something needs fixing.
- **When a game closes right away**: Cornerplay reads its log and says why in plain words (no Vulkan, missing Visual C++ or .NET, anti-cheat, missing files, a crash inside Proton, a full drive) with a fix button: Install Visual C++ / .NET (winetricks through umu), Repair files, Try another Proton, Open log, ProtonDB.
- **Downloads one at a time**: installs, updates, repairs and moves queue up ("Queued" on the cover) instead of slowing each other down; Cancel takes a game out of the line.
- **Space check before installing**: if the drive would drop under 10% free (Epic says how big a game is; for the others the current free space counts), Cornerplay asks first and suggests big games you haven't played for three months.
- **Overnight updates** (Settings > Library): Epic, GOG and Amazon updates between two hours you choose, only on mains power and not on a metered connection, while Cornerplay is open.
- **Leftover Proton prefixes** (Storage): prefixes of games no longer installed, and old ones put aside by Reset, with their size and Delete.
- **Backup and restore** (Settings > People & sync): one zip with settings, people, collections, notes and playtime (no sign-in tokens); restoring keeps a copy of what was there.
- **Animated covers and banners** in TV mode (SteamGridDB key; only when plugged in).
- **Add games** (the Add button): any Windows program (runs through Proton in its own prefix) or Linux program, with covers, playtime, Options and TV mode like the rest; listed under "Other games" (removing one leaves its files alone). Import games already installed: a folder of GOG games, an Epic or Amazon game's folder (legendary / nile import), or everything Heroic installed (native or Flatpak Heroic). Nothing is downloaded again.
- **Native Linux GOG games**: games with a Linux version install it by default (Settings > Compatibility, or per game under Options > Version) and start with their own start.sh, no Proton. Cloud saves are off for them (GOG's save locations are Windows paths). A missing system library is explained, with a way back to the Windows version.
- **Proton-CachyOS**: Settings > Compatibility downloads the newest build from CachyOS (the faster x86-64-v3 build on CPUs that support it), beside GE-Proton.
- **Save backups**: before a game starts, its saves are zipped into `~/.local/share/cornerplay/backups` (the last 5 per game; skipped when nothing changed). Where each game keeps its saves comes from [Ludusavi's manifest](https://github.com/mtkennerly/ludusavi-manifest) (20,000+ games), read inside the game's Proton prefix (Steam's too) or your home for Linux versions. A game's More > Save backups: Back up now, Restore (what is there first gets backed up too), Open folder. Needs PyYAML (the installer adds it).
- **Updates**: an installed Cornerplay checks GitHub once a day and offers the new version (Update, then Restart). Settings: `update_check`.
- **Free on Epic**: this week's free Epic games (and the next ones) above the library, from Epic's public promotions feed. Get opens the store page (Epic lets no other app claim them); claimed games show up on the next refresh.
- **Steam achievements**: progress (12 / 50) in a Steam game's panel and in TV mode, when a Steam Web API key is set.
- **Battle.net owned games**: Accounts > Battle.net > Link account signs in to your Blizzard account (kept in its own browser profile); every refresh then lists the Blizzard games you own but have not installed. Install opens the Battle.net app on that game.
- **ProtonDB**: each game matched to Steam shows its [ProtonDB](https://www.protondb.com) rating (Platinum, Gold, Silver, Bronze, Borked), from players' reports of how it runs on Linux: a badge on the cover while it is pointed at or selected (Settings > Appearance to turn it off), a label in the game panel that opens the game's ProtonDB page (with the trending tier when it differs), and in TV mode. Fetched in the background after a refresh, cached for a week (`protondb.py`).
- **About each game**: description, genres, developer and release year in the game panel and in TV mode, from GOG for GOG games, from Steam's store for any game matched to Steam, or the store's own text (`details.py`, cached for a month).

## Status and licence

Early software: the store sign-in, install and launch paths are built against the
legendary, gogdl and nile command lines but have had little real-world testing. Cornerplay is
not affiliated with Valve, Epic Games, GOG, Amazon or Blizzard. MIT licensed, see `LICENSE`.
