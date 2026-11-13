<p align="center"><img src="docs/banner.jpg" alt="Cornerplay: your games, in one cozy place"></p>

<p align="center">
  <b>Steam, Epic Games, GOG, Amazon Games, Battle.net and Humble Bundle in one cosy library on Linux,<br>
  with a couch-friendly TV mode for your controller.</b>
</p>

<p align="center">
  <a href="https://raulgbh-ctrl.github.io/cornerplay/"><b>Website</b></a> ·
  <a href="https://github.com/raulgbh-ctrl/cornerplay/releases/latest"><b>Download</b></a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#setting-up-each-store">Store setup</a> ·
  <a href="#requirements">Requirements</a> ·
  <a href="#all-the-features">Features</a>
</p>

<p align="center"><img src="docs/screenshot-library.jpg" alt="The library: the game you played last up front, Continue playing, and your whole collection"></p>

<table>
  <tr>
    <td width="50%"><img src="docs/screenshot-tv.jpg" alt="TV mode, for the couch and a controller"></td>
    <td width="50%"><img src="docs/screenshot-game.jpg" alt="A game's page: play, DLC, favourites, status, notes"></td>
  </tr>
  <tr>
    <td align="center"><sub>TV mode: big covers, the game's own art, controller first</sub></td>
    <td align="center"><sub>A game's page: Play, DLC, your notes and rating</sub></td>
  </tr>
</table>

<p align="center"><img src="docs/tv-mode.gif" width="800" alt="TV mode with a controller: moving along a shelf, the main menu, the on-screen keyboard"></p>

Pull up a chair. Cornerplay gathers every game you own into one warm, quiet place, so the
one you want is always right there: covers that keep up with the stores, the game you played
last waiting up front, a TV mode laid out like SteamOS Game Mode, and Proton sorted out behind
the scenes. No more hopping between five launchers to find something to play tonight.

*Formerly AIO Launch (and before that, Kura): settings, sign-ins and games come along by
themselves, and the old `aiolaunch` command keeps working.*

## Quick start

1. **Install.** Download `cornerplay.run` from the
   [latest release](https://github.com/raulgbh-ctrl/cornerplay/releases/latest) and run it:

       curl -fLO https://github.com/raulgbh-ctrl/cornerplay/releases/latest/download/cornerplay.run && sh cornerplay.run

   **Arch / CachyOS / Manjaro** can install it as a package instead (an AUR upload is coming):

       git clone https://github.com/raulgbh-ctrl/cornerplay && cd cornerplay/packaging/aur && makepkg -si

   The installer looks at what your PC still needs, shows it as one list and asks once (press
   Enter for all of it; system packages go in with a single password prompt). Controller support
   is always set up: your system's SDL2, or a private copy when there is none.

   No root needed for Cornerplay itself. It adds itself to your app menu and fetches what games
   need (it asks before installing Steam through your package manager or Flathub).
2. **Connect a store.** Open Cornerplay, click the person icon at the bottom of the sidebar
   (**Accounts**) and sign in to a store. Steam needs no sign-in: if the Steam client is
   installed and you are signed in there, your games show up by themselves.
3. **Play.** Double-click a cover (or select it and press Enter). Not installed yet? Its page has
   an Install button; Proton is chosen and set up for you. Press **F11** (or the Guide button on
   a controller) for TV mode.

## Setting up each store

| Store | How to connect | Needed? |
|-------|----------------|---------|
| **Steam** | Nothing: Cornerplay reads the Steam client on this PC. Games install and start through Steam. | The Steam client (the installer offers it). |
| **Epic Games** | Accounts > Epic Games > Sign in: a sign-in window opens; Cornerplay keeps the session through [legendary](https://github.com/derrod/legendary). | Nothing else. |
| **GOG** | Accounts > GOG > Sign in. Installs go through [gogdl](https://github.com/Heroic-Games-Launcher/heroic-gogdl); Linux versions are used when a game has one. | Nothing else. |
| **Amazon Games** | Accounts > Amazon Games > Sign in, through [nile](https://github.com/imLinguin/nile). | Nothing else. |
| **Battle.net** | See below. | The Battle.net app, under Proton. |
| **Humble Bundle** | Accounts > Humble Bundle > Sign in: log in on Humble's page in the sign-in window (or paste your `_simpleauth_sess` cookie). Every DRM-free game in your library (bundles, the store, Humble Choice) is listed; the Linux download installs when there is one (archives and MojoSetup `.sh` installers are unpacked without running them), otherwise the Windows one through Proton (an installer runs once in its own window). Steam keys show up through Steam once redeemed. | Nothing else. |

**Steam Web API key (optional).** Without one, Cornerplay lists the Steam games in your Steam
client's library. With one it also lists every game you own (even ones Steam has never shown on
this PC) and shows achievement progress. Get a key at
[steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey) (any domain name works, e.g.
`localhost`) and paste it in **Settings > Library**. If the list or achievements stay empty, set your
Steam profile's *Game details* to Public.

**SteamGridDB key (optional).** Cornerplay finds covers on its own (store art, Steam's store,
IGDB). A free [SteamGridDB](https://www.steamgriddb.com) key adds art for games Steam doesn't sell,
better wide banners and animated covers in TV mode: sign in there, open
[Preferences > API](https://www.steamgriddb.com/profile/preferences/api), generate a key and paste
it in **Settings > Library**.

**Battle.net under Proton.** Blizzard has no API for other launchers, so Cornerplay runs
Blizzard's own app:

1. In the library, the **Battle.net** tile is the app itself. Press Install: Cornerplay downloads
   Blizzard's installer and runs it in its own Proton prefix.
2. Press Play on the tile and sign in inside the Battle.net app. Install your games there.
3. Back in Cornerplay, each installed game appears as its own tile and starts straight into the
   game. To also see Blizzard games you own but haven't installed, use
   **Accounts > Battle.net > Link account**.

If the Battle.net app closes as soon as it opens, your GPU has no Vulkan driver: the
**Health check** in the sidebar says which package to install (for Intel graphics on Arch:
`vulkan-intel lib32-vulkan-intel`).

## Requirements

- **Linux**, 64-bit. Developed and tested on **CachyOS (Arch)** with Hyprland and KDE Plasma; the
  installer also knows Debian/Ubuntu (apt), Fedora (dnf) and openSUSE (zypper), which have had
  less testing. Steam Deck: works in Desktop Mode and from Game Mode (add it to Steam from
  Settings > Library), lightly tested.
- **Python 3.10+** and **PySide6 (Qt 6.6 or newer)**. If your system has no PySide6, the installer
  sets up a private copy (about 260 MB).
- **A GPU with a Vulkan driver**, for games running through Proton (Epic, GOG, Amazon,
  Battle.net). Steam games use Steam's own setup.
- **Disk space**: Cornerplay itself about 6 MB; each Proton version about 1.5 GB; the cover cache
  grows to a few hundred MB for a large library (about 300 MB for 500 games). Games install to
  `~/Games/cornerplay` by default (changeable in Settings).
- **Steam** for Steam games, and **umu-launcher** for the other stores (the installer fetches
  a copy if your package manager has none). Optional: MangoHud, GameMode.

Files: settings in `~/.config/cornerplay`, the cover cache and logs in `~/.cache/cornerplay`,
games and Proton prefixes in `~/Games/cornerplay`.

To remove it:

    sh ~/.local/lib/cornerplay/install.sh --uninstall   # remove (keeps settings and games)
    sh ~/.local/lib/cornerplay/install.sh --purge       # also remove settings and cache

## Privacy and security

- **Your keys and sign-ins stay private**: Cornerplay's settings folder (API keys, the GOG
  sign-in) and the Epic and Amazon sign-ins it makes through legendary and nile are readable
  only by your user account; Cornerplay tightens folders left open by older versions (or by those
  tools) every time it starts. API keys never show in error messages.
- **Backups leave secrets out**: settings backups contain no sign-in tokens and no API keys,
  are readable only by you, and restoring one only ever writes inside Cornerplay's own folders.
- **Downloads are checked**: updates of Cornerplay itself, legendary, gogdl, nile, umu-launcher
  and Proton builds are checked against the checksums their publishers list before they are
  used. Cornerplay updates itself only from this project's own GitHub releases, and never when
  pacman or Flatpak installed it (they update it instead).
- **Links and store text**: only web and `steam://` links are opened; store descriptions are
  shown as plain text.
- **Sync folder**: data from other PCs is checked before it is merged; anything malformed is
  left out.

## Command line

    cornerplay                  # open the library
    cornerplay --tv             # start in full-screen TV mode (F11 switches)
    cornerplay --background     # start in the tray (how "Start with the PC" opens it)
    ./install.sh --session      # add "Cornerplay (TV)" to the login screen (TV mode in gamescope)
    cornerplay --status         # what each store still needs
    cornerplay --overlay        # open or close the in-game panel of the running Cornerplay
    cornerplay --demo           # a sample library; nothing is launched

| Store      | Library from                         | Install / launch through            |
|------------|--------------------------------------|-------------------------------------|
| Steam      | Steam's own cache `appinfo.vdf` (or every owned game with a Web API key) | the Steam client (`steam://` URLs)  |
| Epic       | `legendary list`                     | legendary + Proton (umu-run)        |
| GOG        | GOG web API                          | gogdl + Proton (umu-run), or the Linux version |
| Amazon     | `nile library sync`                  | nile + Proton (umu-run)             |
| Battle.net | the Battle.net app's `product.db`    | the Battle.net app under Proton     |

## All the features

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
- **Screenshots and trailers**: the game panel shows the game's screenshots (click one to see it full size; arrow keys to browse), and **your own**: Steam's (F12) and any screenshot taken while the game ran, with any tool, from ~/Pictures/Screenshots or ~/Pictures (`screenshots.py`). In TV mode the focused game's art slowly pans, and after a couple of seconds its trailer plays muted behind the text (Settings > Appearance; needs Qt Multimedia, otherwise it is simply left out; never plays while a game has the focus). Optional soft navigation sounds in TV mode (off by default; synthesised, `cornerplay/sounds/`).
- **Languages**: English and Română (Settings > Appearance > Language; Automatic follows the system). Translations are Qt `.ts` files in `cornerplay/i18n/`: `cornerplay/i18n/update.sh` refreshes them after the interface changes, and a new language is a copy of `cornerplay_ro.ts` translated in Qt Linguist (the script's header says how).
- **Fonts**: [Nunito](https://github.com/googlefonts/nunito), rounded like the logo, for the interface (fixed weights made from the variable font; SIL Open Font Licence, `cornerplay/fonts/OFL-Nunito.txt`), bundled so the app looks the same on every desktop. For game titles (Settings > Appearance) also [Barlow Condensed](https://github.com/jpt/barlow), [Lora](https://github.com/cyrealtype/Lora-Cyrillic) and [Silkscreen](https://github.com/googlefonts/silkscreen), all SIL Open Font Licence (`cornerplay/fonts/OFL-*.txt`). TV mode's background music is an original loop made from sine waves by `packaging/make-ambient.py`.
- **The look**: the C-and-play-button icon, and a logo that takes its colours from your theme (your wallpaper's colours; `cornerplay/art/brand/`), warm amber as the signature colour (the default "Cornerplay" theme; Follow wallpaper and the other presets are still in Settings > Appearance), store logos on coloured tiles, little scenes for empty screens (drawn in the theme's colours, `qml/EmptyScene.qml`), frosted pop-ups and notifications, a launch card when a game starts (its cover lifts and glows while it gets ready), a short splash while the library loads, and in TV mode a shelf reflection under the covers and an optional start-up animation with a chime. Cover shadows: none, soft or deep. With Follow wallpaper the wallpaper itself sits blurred behind the window, like frosted glass (Settings > Appearance; no compositor blur needed). Covers tilt toward the pointer with a soft light following it; a cover flies into the game page when opened and back when closed; pointing at a cover for a moment plays its trailer inside it, past the ratings boards and publisher logos at its start (Settings > Appearance); Steam covers show a thin bar of achievements earned (gold when complete); in the evening the surfaces turn a little warmer (Settings > Appearance); store and shelf changes slide in. Downloads show their speed and time left (game page, TV mode, Quick Access), and a desktop notification says when one finishes while Cornerplay is in the background. The logo animates in on the splash and the TV intro (the C swings round, the play button pops, the sparks flick on).
- **Button icons**: from [Lucide](https://lucide.dev) (ISC licence), in `cornerplay/icons/ui/`.
- **Store and ProtonDB logos**: from [Simple Icons](https://simpleicons.org) (CC0), in `cornerplay/icons/`. The logos are trademarks of their owners and are only used to show which store a game belongs to.
- **Themes**: follow the Ryoku desktop palette, presets, or your own accent + background; cover size, corner radius, badges (Settings > Appearance).
- **Light and dark, backgrounds, spacing and fonts** (Settings > Appearance): switch between a light and a dark preset with the desktop (Qt, else the portal's color-scheme) or at sunset; behind the library a slowly moving gradient, the last played game's art or a picture of your own, softly blurred (a collection can have its own picture: the × next to it); compact, comfortable or roomy space between covers; game titles in Rounded, Condensed, Serif or Pixel type; small seasonal touches on empty screens and the splash (snow, leaves, petals, fireflies).
- **Ways to see the library** (View): Covers, Logos (wide art with the game's logo), Boxes (game cases with a spine, on wooden shelves), Shelves (rows like TV mode's: Continue playing, your lists, Play together, your biggest genres) and List.
- **Proton**: every Proton build on the PC is offered, wherever it was installed: Valve's builds in any Steam library, Steam's compatibilitytools.d (ProtonUp-Qt, ProtonPlus, Cornerplay's GE-Proton download; also Flatpak and Snap Steam), Heroic, Lutris, umu, system packages and `STEAM_EXTRA_COMPAT_TOOLS_PATHS` (`protons.py`). Default version in Settings > Compatibility; per-game Proton, MangoHud, GameMode, env vars and launch arguments under a game's Options.
- **Proton for Steam games**: a Steam game's Options sets Steam's own per-game compatibility tool (Properties > Compatibility): Valve's builds (Steam downloads them when needed) and every other build on the PC; one that lives outside Steam (Heroic, Lutris, ...) is linked into Steam's compatibilitytools.d when chosen. Steam is closed and reopened around the change, and `config.vdf` is backed up first (`steamcompat.py`).
- **TV mode / controller** (`cornerplay/gamepad.py`, SDL2: the system's, or a private copy Cornerplay downloads and checks by itself, `sdl.py`), laid out like SteamOS Game Mode: D-pad or stick = move (held, it speeds up), up/down = shelf, LT/RT = jump a screen, A = play, Start/Menu (or X) = the game's options, Guide (Xbox / PS / Home button) = the main menu sliding in from the left (Home, Search, Installed only, Next store, Exit TV mode, Quit), Guide + A or Share = quick access from the right (now playing with Quit, downloads with progress, sound / trailer / animated-art switches), Y = installed only, LB/RB = store, View/Select = search (an on-screen keyboard with numbers on top, QWERTY letters, a dash and an apostrophe, and a wide space bar; X deletes, Y types a space, View/Select is done), B = back (clears a search, then returns to the top shelf, then opens the main menu). Keyboard: F10 main menu, F9 quick access, F2 options, F11 leaves TV mode; Guide (F10) in the desktop window opens TV mode. Keyboard: arrows, Shift+arrows, Home/End, and just type to search. Shelves: Continue playing, Favourites, your collections, Recently added, Library. A clock and the battery level (Steam Deck, laptops) sit top right. The on-screen hints use the connected pad's own glyphs: Xbox (also the Steam Deck), PlayStation, or Nintendo (labelled by position).
- **Favourites and collections**: star a game (its panel, or TV mode's actions) and make your own collections ("Co-op nights", "Backlog"); they sit in the sidebar under the stores and are shelves in TV mode. Kept per game in `~/.config/cornerplay/games.json`.
- **Backlog, ratings and notes**: mark a game Playing, Want to play, Finished or Dropped, give it 1-5 stars and a note ("stuck on boss 3") in its panel. Statuses show in the sidebar and as TV shelves; sort the library by your rating.
- **Stats**: sidebar > Stats. Overview: hours played in total and per store, games played vs never started, your most played, the last two weeks and the last 12 weeks, and how much of your backlog (Playing, Want to play, Finished) is finished. Your year: hours, games played, games started for the first time and finished, hours per month, the busiest month, the longest session and the year's most played; earlier years too (`statsdata.py`). Cornerplay logs each session of the games it starts, and of Steam games while it runs (`steamrun.py`); Steam's own totals have no dates.
- **Storage**: sidebar > Storage: every installed game by size, how full each drive is, Free up space (games over 2 GB not played for three months), Uninstall, and Move to another folder or drive (Epic, GOG and Amazon, with progress; Steam games move in Steam's Settings > Storage; Battle.net in its app).
- **Gamescope**: run Epic, GOG, Amazon and added games inside Valve's [gamescope](https://github.com/ValveSoftware/gamescope): full screen at your screen's resolution (for games that pick the wrong size or fight the desktop over full screen), or drawn at two thirds of it and upscaled with AMD FSR for more frames; optional HDR. With MangoHud on, gamescope's own overlay is used. Default in Settings > Compatibility, per game under Options. Never nested inside Steam's Game Mode (already gamescope) and never around the Battle.net app.
- **Performance profiles**: Battery saver (30 fps), Balanced (60 fps), both with FSR upscaling, or Max quality; an FPS counter (MangoHud). Default in Settings > Compatibility, per game under Options (Epic, GOG, Amazon). Each game keeps its own shader cache (`~/.cache/cornerplay/shaders`) so only the first run stutters.
- **Fix it** (a game's Options): Repair files (Epic, GOG, Amazon), Reset Proton prefix (the old one is renamed, not deleted), Open log.
- **Controller support**: from Steam's store data, in the game panel and TV mode; Steam games that are not fully supported link to Steam's controller layout.
- **TV mode, more of it**: Who's playing? at start when several people use the PC; X / More opens a game's own page (art, playtime, achievements, time to beat, your screenshots and the store's, Play, Options, Favourite); the Guide menu has Downloads (pause, resume, reorder, cancel), Your stats (the year in big type), Sleep / Restart / Shut down (a second press confirms) and Play on your gaming PC; a Play together shelf for local and split-screen multiplayer (first when two or more controllers are connected; `couch.py`, from Steam's own app cache); a screensaver of your recently played games after a few quiet minutes; optional calm background music and controller rumble.
- **Boot into TV mode**: `./install.sh --session` (or the AUR package) adds "Cornerplay (TV)" to the login screen: TV mode as the whole session, full screen in gamescope, like SteamOS Game Mode (`cornerplay/session/`). Switch to desktop in its menu ends the session.
- **Play on another screen** (Settings > Advanced): Add Cornerplay to Sunshine puts TV mode and your favourites in Sunshine's app list for Moonlight on a TV, laptop or Deck; on the screen's side, set your gaming PC (and its MAC address) and TV mode can wake it (Wake-on-LAN) and stream its TV mode through Moonlight (`stream.py`).
- **Tray and starting with the PC**: while a game runs Cornerplay steps aside into the tray and comes back when it closes; the tray menu quits the running game or starts a recent one. Settings > Advanced: keep running in the tray when the window is closed, and start with the PC (in the tray). Starting Cornerplay again shows the window that is already running (`tray.py`).
- **What should I play?** (Tools menu, Ctrl+P): one pick and two others, each with its reason (you are in the middle of it, you left it a month ago, you often play it at this hour, it plays on one screen together); choose how long you have (half an hour, an evening) and whether you play alone or together on one screen, and Three more deals again. Never finished or dropped games.
- **Will it run on this PC?** A game's page compares its Steam requirements with your graphics card (its video memory too), processor, memory and free space, and says Runs well, Should run, Borderline (lower settings) or Probably too much, with the line that falls short; games whose anti-cheat blocks Linux say so (from [Are We Anti-Cheat Yet](https://areweanticheatyet.com)). Requirements are cached for a month (`compat.py`).
- **Fixes, one click away**: under the verdict, the usual remedies for a Proton game as switches: GE-Proton, NVAPI (DLSS on NVIDIA), WineD3D for old DirectX games, no V-Sync, large address aware, hide the NVIDIA card. Cornerplay suggests one after a session that ended badly; each just edits the game's Options.
- **How it ran**: Settings > Compatibility > Record how games run logs each session with MangoHud (hidden unless you show it) and keeps the numbers on the game's page: average FPS, 1% low, stutters, the hottest the CPU and GPU got, and the averages per Proton version so you can see which runs it better (`perf.py`).
- **Saves follow you between PCs**: with a sync folder (Settings > People & sync) and save backups on, a game's saves are shared when you stop playing; on the other PC, Cornerplay sees the newer save before the game starts and asks whether to use it (the local saves are backed up first). Steam and stores with their own cloud saves are left to them.
- **Play with friends** (Tools menu): your Steam friends, online first with what they are playing; pick who's in and see the multiplayer games you all own (or most of you), with the hours between you, Play / Install, and Copy invite (a `steam://run` link to paste in chat). Needs a Steam Web API key (`friends.py`).
- **In-game panel**: Guide + Y on a controller (works while a game has the focus), Ctrl+Shift+G, or `cornerplay --overlay` bound to a key in your desktop's settings opens a small panel over the game: the time, the battery, how long this session has run, the screenshots taken so far, the game's note to edit, and Back to the game, Open Cornerplay or Quit (pressed twice). On Wayland the desktop decides whether it may sit over a full-screen game.
- **Players with a PC like yours**: a game's page shows the ProtonDB reports from graphics cards like yours (the same card first, then the same maker and similar power) that got it running: their Proton, launch options and notes. "Use these settings" puts their Proton (when this PC has that build, or GE-Proton), environment variables, launch arguments, GameMode and MangoHud into the game's Options; for Steam games the launch options are copied to paste into Steam. From ProtonDB's open data dump (ODbL), read once a month in the background, keeping only your games' reports (`pdbreports.py`; Settings > Compatibility).
- **Before it starts, after it closes** (a game's Options): commands to run first (connect a VPN, mount a drive; a line ending in & is left running, like Discord) and after it closes (power mode back to balanced, close Discord). One-click presets for Discord and the performance power mode (`steps.py`).
- **Prism Launcher**: your Minecraft instances are games in Cornerplay, with the Minecraft version, mod loader (Fabric, Forge, NeoForge, Quilt), number of mods and the time Prism counted; Play starts the instance through Prism, and "Open in Prism Launcher" (right-click) gets to its mods and worlds. Native or Flathub Prism, and a custom instance folder (`stores/prism.py`).
- **Shaders ready after a driver update**: while a game from Epic, GOG, Amazon, Humble or your own runs, its shaders are recorded with Steam's Fossilize (the layer Steam installs); after a Mesa or NVIDIA update they are built again in the background, one game at a time, at the lowest priority, on mains power and while nothing is played, so the first run after the update does not stutter (Settings > Compatibility; `shaders.py`). Steam does the same for its own games.
- **Easy Anti-Cheat and BattlEye**: when Steam's free "Proton EasyAntiCheat Runtime" or "Proton BattlEye Runtime" tool is installed (in any Steam library), Epic, GOG, Amazon and the other games Cornerplay runs through Proton use it too (`PROTON_EAC_RUNTIME`, `PROTON_BATTLEYE_RUNTIME`), as Steam does for its own. A game whose anti-cheat works on Linux but whose runtime is missing says so on its page, with Install in Steam. The game's developer still has to allow Linux.
- **Denuvo warning**: a game with Denuvo (from Steam's store data) says so on its page, and changing its Proton version (Options, or the GE-Proton switch) asks first: Denuvo can count each change as a new PC and allows only a few a day.
- **Many games at once**: Ctrl+click picks a game, Shift+click a range, Ctrl+A everything shown; a bar at the bottom favourites, adds to a collection, sets the status, installs, updates or hides them all. Esc lets go.
- **Game settings on every PC**: with a sync folder, each game's Proton version, MangoHud, GameMode, gamescope, performance profile, environment, launch arguments, Linux/Windows version and hidden state are the same on every PC; the newer change wins. A Proton build is matched by name, and a PC without it keeps its own choice (`gamesync.py`).
- **Tools menu** (bottom left): What should I play, Stats and journal, Screenshots, Play with friends, Storage, Health check, Hidden games and Keyboard shortcuts in one labelled menu, next to Accounts and Settings.
- **Small windows**: under about 980 px wide the sidebar folds into a rail of icons (names as tooltips), so half a screen or a small laptop still has room for the covers and a game's page.
- **New games**: a game bought or claimed in the last week wears a small NEW ribbon on its cover until you play it (games you already owned when a store was connected never do).
- **Smart lists**: pick filters (a store, installed only, never played, Linux version, controller support, play together, ProtonDB Gold+, genres) and Save as a list: it sits under Your lists in the sidebar with a live count, and always shows what those filters find, new games included.
- **Screenshots page** (Ctrl+Shift+S, the images icon in the sidebar): every game's screenshots in one place, newest game first: Steam's F12 ones for every app, and any picture in your screenshot folders taken while a game ran. Click one to browse that game's shots full size.
- **Journal** (Stats > Journal): your play history month by month: hours, each game with its hours and sessions, and what you started and finished that month.
- **Jump anywhere (Ctrl+K)**: type a few letters to jump to a game (Enter opens its page, Shift+Enter plays it) or an action: Settings, Stats, a store, a view, TV mode and more. With nothing typed it lists your recent games.
- **Your sessions** on a game's page: the last few times you played it (date, time, how long) and its hours in the last 30 days.
- **Forgiving search**: words in any order, accents and punctuation ignored, roman numerals read as numbers, and a game's initials: "witcher 3", "baldurs gate", "gta 5", "rdr2" and "hk" all find their game (`search.py`).
- **After a session**: when a game you played for a few minutes closes, a small card says how long you played and your total, with stars to rate it, I finished it and a note (where you got to), so your backlog and ratings fill in as you go.
- **Keyboard shortcuts**: F1, ? or the keyboard icon in the sidebar shows every key on one card. Ctrl+F search, Ctrl+R refresh, Ctrl+N add a game, Ctrl+P What should I play?, Ctrl+I Stats, Ctrl+, Settings, F11 TV mode, Ctrl+Q quit.
- **Now playing**: a bar (and a TV chip) while a game started from Cornerplay runs, with Quit and Force close.
- **People**: Settings > People & sync: each person has their own favourites, collections, statuses, stars, notes and stats; switch at the top of the sidebar.
- **Sync between PCs**: pick a folder Syncthing / Nextcloud / Dropbox already syncs; personal data merges game by game and playtime adds up across PCs.
- **Health check** (sidebar): Vulkan, Proton runner and versions, store tools, Steam, sign-ins, disk space, the sign-in window and controller support, each with a fix (a download, a sign-in, or the exact command to copy). The sidebar shows "!" when something needs fixing.
- **When a game closes right away**: Cornerplay reads its log and says why in plain words (no Vulkan, missing Visual C++ or .NET, anti-cheat, missing files, a crash inside Proton, a full drive) with a fix button: Install Visual C++ / .NET (winetricks through umu), Repair files, Try another Proton, Open log, ProtonDB.
- **Downloads**: installs, updates, repairs and moves go one at a time ("Queued" on the cover) instead of slowing each other down. The Downloads button (top bar, while anything downloads) lists them with speed and time left: move waiting ones up or down, pause an Epic, GOG or Amazon install or update and resume it later (the store tool carries on where it stopped), or cancel. A speed limit for Epic, GOG and Amazon downloads (the panel or Settings > Library) keeps room for everything else on your internet (`throttle.py`: the tool is frozen for part of every half second, steered by the speed it reports).
- **Space check before installing**: if the drive would drop under 10% free (Epic says how big a game is; for the others the current free space counts), Cornerplay asks first and suggests big games you haven't played for three months.
- **Overnight updates** (Settings > Library): Epic, GOG and Amazon updates between two hours you choose, only on mains power and not on a metered connection, while Cornerplay is open.
- **Leftover Proton prefixes** (Storage): prefixes of games no longer installed, and old ones put aside by Reset, with their size and Delete.
- **Backup and restore** (Settings > People & sync): one zip with settings, people, collections, notes and playtime (no sign-in tokens); restoring keeps a copy of what was there.
- **Animated covers and banners** in TV mode (SteamGridDB key; only when plugged in).
- **Add games** (the Add button): any Windows program (runs through Proton in its own prefix) or Linux program, with covers, playtime, Options and TV mode like the rest; listed under "Other games" (removing one leaves its files alone). Import games already installed: a folder of GOG games, an Epic or Amazon game's folder (legendary / nile import), or everything Heroic installed (native or Flatpak Heroic). Nothing is downloaded again.
- **Native Linux GOG games**: games with a Linux version install it by default (Settings > Compatibility, or per game under Options > Version) and start with their own start.sh, no Proton. Cloud saves are off for them (GOG's save locations are Windows paths). A missing system library is explained, with a way back to the Windows version.
- **Proton-CachyOS**: Settings > Compatibility downloads the newest build from CachyOS (the faster x86-64-v3 build on CPUs that support it), beside GE-Proton.
- **Save backups**: before a game starts, its saves are zipped into `~/.local/share/cornerplay/backups` (the last 5 per game; skipped when nothing changed). Where each game keeps its saves comes from [Ludusavi's manifest](https://github.com/mtkennerly/ludusavi-manifest) (20,000+ games), read inside the game's Proton prefix (Steam's too) or your home for Linux versions. A game's More > Save backups: Back up now, Restore (what is there first gets backed up too), Open folder. Needs PyYAML (the installer adds it).
- **Updates**: Cornerplay checks GitHub once a day and offers the new version (Update, then Restart); Settings > Advanced > Check now asks at once. A copy that runs from a git folder is updated with `git pull` the same way (only when the folder has no changes of its own). Settings: `update_check`.
- **Retro games**: add your ROM folders (Settings > Library > Retro games) and every ROM becomes a game, with box art from the libretro thumbnail server, playtime, favourites and TV mode, played full screen in RetroArch (installed, or from Flathub) with the first core it has for the system. NES, SNES, Game Boy (Color / Advance), N64, DS, Mega Drive, Master System, Game Gear, PlayStation, PSP, PC Engine, Atari 2600, Dreamcast and arcade; a folder per system works best (.iso, .chd and .zip files take their system from the folder's name). Multi-disc games once, through their .m3u. The Health check says which systems still need a core (`stores/retro.py`).
- **Wishlist sales**: games on your Steam and GOG wishlists that are on sale right now, biggest discount first, above the library (with the price before and after); a toast when one goes on sale. Steam's wishlist needs your profile's game details public; GOG's needs the GOG sign-in. Prices in your country's currency (your GOG account's country, or Settings > Library). Checked every 6 hours (`wishlist.py`). With a free [IsThereAnyDeal](https://isthereanydeal.com) API key (Settings > Library) each wishlist game also gets its cheapest deal on any store (Humble, Fanatical, Epic, ...) and its lowest price ever; a deal at least as deep as you choose, or a new lowest price, comes as a desktop notification (`itad.py`). With the same key, a home row lists games free to keep on other stores right now (GOG, Prime Gaming, Steam, Fanatical, ...).
- **Mods**: a game's page has Mods for the games Cornerplay can mod: Valheim, Lethal Company, Risk of Rain 2, R.E.P.O., PEAK, Content Warning and other BepInEx games from Thunderstore (a mod's dependencies, BepInEx first, come with it), and Stardew Valley (SMAPI), Skyrim Special Edition, Fallout 4 and Cyberpunk 2077 from Nexus Mods (FOMOD installers run with their recommended choices; Skyrim and Fallout plugins are switched on in plugins.txt). Switch mods on and off, keep profiles (Co-op, Vanilla+...), update them, or Play without mods. Each mod is kept in its own folder and copied into the game; the game files a mod replaced are put back when it is switched off (`mods.py`). Nexus downloads need your free API key: Premium installs at once, a free account presses "Mod Manager Download" on Nexus (Cornerplay can take those `nxm://` links).
- **Steam Workshop on the Mods page**: an installed Steam game with Workshop subscriptions gets Mods on its page, listing them (title, picture, size, last update) with Open in Steam to unsubscribe there and Browse the Workshop; Steam lets no other app change subscriptions (`workshop.py`).
- **Clean up** (Storage): shader caches Steam keeps for games no longer installed, crash dumps over a day old in game folders and their Proton prefixes, and the DirectX / Visual C++ installers (_CommonRedist, __redist) of games already played, each with its size and Clean up; saves, settings and prefixes are never touched (`cleanup.py`).
- **Patch notes**: a game's page shows the developer's latest announcements from Steam (also for games bought elsewhere), marking the ones posted since you last played (`patchnotes.py`).
- **Humble Bundle page**: this month's Humble Choice games (marked when already yours) and the game bundles on sale, with prices and end dates, from Humble's public pages (`humbleshop.py`). A bundle opens its tiers: every game in each, the ones you own marked, and (with an IsThereAnyDeal key) what the games cost separately today at the cheapest store, against the tier's price, also counting only the games you don't own.
- **Store** (sidebar, the red gift): everything to grab or buy on one page: free games to keep (Epic's and other stores' giveaways), sales on your wishlist, Humble Choice and Humble's game bundles (with each tier priced against buying separately) and Steam bundles priced for you. It took Humble Bundle's place in the sidebar (Humble shows again only if it has games of yours), and free games and sales are no longer on the home page.
- **Steam bundles**: the Steam page shows bundles with your wishlist games (the cheapest way to each first) and Complete the set (bundles that only add DLC or soundtracks to games you own); a Steam game's page lists every bundle it is in. Each is priced for you, as Steam does: the sum of what you don't own, less the bundle discount (Cornerplay can't see owned DLC, so the real price can be lower) (`steambundles.py`, Steam's public store API).
- **Free on Epic**: this week's free Epic games (and the next ones) on the Store page, from Epic's public promotions feed. Get opens the store page (Epic lets no other app claim them); claimed games show up on the next refresh.
- **Achievements**: progress (12 / 50) in a game's panel, in TV mode and as a thin bar on its cover: Steam games when a Steam Web API key is set, GOG games when you are signed in to GOG (from GOG Galaxy's own achievement service, with a token made for that game from your sign-in). Epic keeps achievements to its own launcher.
- **Battle.net owned games**: Accounts > Battle.net > Link account signs in to your Blizzard account (kept in its own browser profile); every refresh then lists the Blizzard games you own but have not installed. Install opens the Battle.net app on that game.
- **ProtonDB**: each game matched to Steam shows its [ProtonDB](https://www.protondb.com) rating (Platinum, Gold, Silver, Bronze, Borked), from players' reports of how it runs on Linux: a badge on the cover while it is pointed at or selected (Settings > Appearance to turn it off), a label in the game panel that opens the game's ProtonDB page (with the trending tier when it differs), and in TV mode. Fetched in the background after a refresh, cached for a week (`protondb.py`).
- **Discord** (optional, Settings > Advanced): "Playing <game>" on your Discord profile for Epic, GOG, Amazon and added games, which Discord cannot see under Proton (it shows Steam games itself). Needs the desktop Discord app (also Flatpak Discord or Vesktop) and the Application ID of a free Discord application named Cornerplay (`discord.py`).
- **Time to beat** (optional): how long a game takes, main story, with extras and 100%, on its page, from [IGDB](https://www.igdb.com)'s players' reports. Needs a free Twitch developer app (Settings > Library has the steps); matched through Steam's app id, otherwise only by exact title, so a sequel's hours are never shown. Cached with the game's details (`timetobeat.py`).
- **About each game**: description, genres, developer and release year in the game panel and in TV mode, from GOG for GOG games, from Steam's store for any game matched to Steam, or the store's own text (`details.py`, cached for a month).


## For developers

PySide6 + QML. `cornerplay/stores/*.py` has one file per store, `cornerplay/app.py` is the Qt
glue, `cornerplay/qml` is the interface.

    git clone https://github.com/raulgbh-ctrl/cornerplay && cd cornerplay
    ./install.sh --dev           # install a launcher that runs this folder in place
    python3 -m cornerplay --demo # run from the folder with the sample library
    python3 -m cornerplay --check  # compile every QML file and report errors (run before a commit)
    cornerplay --fetch-backends  # download legendary, gogdl and nile into ~/.local/share/cornerplay/bin
    ./make-installer.sh          # build dist/cornerplay-<version>.run (the one-file installer)
    python3 tools/shoot.py out wait:500 shot:library key:F11 wait:3000 shot:tv  # screenshots of the demo, off screen

An Arch package recipe is in `packaging/aur/PKGBUILD` (`makepkg -si` there builds and installs it).

Tests and the lint check (CI runs both, plus the QML check, on every push):

    pip install pytest ruff
    ruff check cornerplay tests
    QT_QPA_PLATFORM=offscreen pytest -q

## Status and licence

Early software: the store sign-in, install and launch paths are built against the
legendary, gogdl and nile command lines but have had little real-world testing. Cornerplay is
not affiliated with Valve, Epic Games, GOG, Amazon or Blizzard. MIT licensed, see `LICENSE`.
