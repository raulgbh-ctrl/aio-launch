"""Colour palettes: follow the desktop wallpaper, a preset, or the user's own two colours."""
import os

from .config import HOME, read_json, settings

RYOKU_PALETTE = HOME / ".cache/ryoku/colors.json"

# name -> (background, accent)
PRESETS = {
    "Cornerplay": ("#1a1410", "#ffb547"),  # the signature look: deep warm brown and lamplight amber, like the icon
    "Midnight": ("#141218", "#d2bcfd"),
    "Graphite": ("#16181c", "#8ab4f8"),
    "Forest": ("#111613", "#8fd6a4"),
    "Ember": ("#191312", "#ffb59c"),
    "Ocean": ("#0f1620", "#7fd0ff"),
    "Sakura": ("#1a1216", "#ffb1c8"),
    "Paper": ("#f6f3ee", "#6750a4"),
    "Daylight": ("#f8f9fc", "#2f6fde"),
    "Linen": ("#f5efe6", "#b4532a"),
    "Mint": ("#f0f6f2", "#1d7a55"),
}
ACCENTS = ["#d2bcfd", "#8ab4f8", "#7fd0ff", "#8fd6a4", "#d7e075", "#ffd166", "#ffb59c", "#ff8a80",
           "#ffb1c8", "#e0e0e0"]
BACKGROUNDS = ["#141218", "#16181c", "#0f1620", "#111613", "#191312", "#000000", "#24273a", "#f6f3ee"]


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(c))) for c in rgb)


def mix(a, b, t):
    ra, rb = _rgb(a), _rgb(b)
    return _hex(ra[i] + (rb[i] - ra[i]) * t for i in range(3))


def luminance(h):
    r, g, b = _rgb(h)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def valid(h):
    if not isinstance(h, str) or len(h) != 7 or h[0] != "#":
        return False
    try:
        int(h[1:], 16)
        return True
    except ValueError:
        return False


def build(bg, accent):
    """Derive the full set of surface/text roles from a background and an accent."""
    dark = luminance(bg) < 0.5
    fg = "#ffffff" if dark else "#000000"
    back = "#000000" if dark else "#ffffff"
    on_surface = mix(bg, fg, 0.90)
    return {
        "background": bg, "surface": bg,
        "surfaceContainerLowest": mix(bg, back, 0.25),
        "surfaceContainerLow": mix(bg, fg, 0.035),
        "surfaceContainer": mix(bg, fg, 0.06),
        "surfaceContainerHigh": mix(bg, fg, 0.10),
        "surfaceContainerHighest": mix(bg, fg, 0.15),
        "outlineVariant": mix(bg, fg, 0.22), "outline": mix(bg, fg, 0.52),
        "onSurfaceVariant": mix(bg, fg, 0.76), "onSurface": on_surface,
        "inverseSurface": on_surface, "inverseOnSurface": mix(bg, fg, 0.12),
        "primary": accent,
        "onPrimary": "#1b1b1f" if luminance(accent) > 0.5 else "#ffffff",
        "primaryContainer": mix(bg, accent, 0.32),
        "onPrimaryContainer": mix(accent, fg, 0.55),
        "error": "#ffb4ab" if dark else "#ba1a1a",
        "dark": dark,
    }


FALLBACK = build(*PRESETS["Midnight"])

# Evening warmth: from 19:00 the surfaces drift a little toward warm lamplight, deepest
# 22:00 to 05:00, gone again by 07:00. Text and the accent stay as they are (contrast).
WARM = "#ff9a4a"
SURFACES = ("background", "surface", "surfaceContainerLowest", "surfaceContainerLow", "surfaceContainer",
            "surfaceContainerHigh", "surfaceContainerHighest", "outlineVariant")


def evening_amount(hour):
    """0 in the day, rising to 1 late at night. hour: a float, 0..24."""
    if 22 <= hour or hour < 5:
        return 1.0
    if 19 <= hour < 22:
        return (hour - 19) / 3
    if 5 <= hour < 7:
        return 1 - (hour - 5) / 2
    return 0.0


def warmed(theme, amount):
    """The theme with its surfaces tinted toward lamplight (amount 0..1; dark themes only)."""
    if amount <= 0 or not theme.get("dark", True):
        return theme
    out = dict(theme)
    for k in SURFACES:
        if valid(out.get(k, "")):
            out[k] = mix(out[k], WARM, 0.07 * amount)
    out["warmth"] = round(amount, 2)
    return out


_wall_cache = {}


def from_wallpaper():
    """Theme built from the desktop wallpaper, or None when it cannot be found."""
    from . import wallpaper
    source, path = wallpaper.find()
    if not path:
        return None
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        return None
    if key not in _wall_cache:
        picked = wallpaper.colours(path)
        _wall_cache.clear()
        _wall_cache[key] = build(*picked) if picked else None
    theme = _wall_cache[key]
    if theme:
        theme = dict(theme, wallpaper=path, wallpaperSource=source)
    return theme


def auto_mode(dark):
    """Light and dark follow the desktop or the clock (Settings > Appearance): the preset to use,
    or "" when the chosen look stays as it is."""
    if settings.get("theme_auto") not in ("system", "sunset") or dark is None:
        return ""
    name = settings.get("theme_dark" if dark else "theme_light") or ("Cornerplay" if dark else "Paper")
    return name if name in PRESETS else ""


def sunset_dark(hour):
    """Dark from 7 in the evening to 7 in the morning."""
    return hour >= 19 or hour < 7


def current(dark=None):
    mode = auto_mode(dark) or settings.get("theme_mode")
    if mode == "custom":
        bg, accent = settings.get("theme_bg"), settings.get("theme_accent")
        if valid(bg) and valid(accent):
            return build(bg, accent)
    if mode in PRESETS:
        return build(*PRESETS[mode])
    # Follow the wallpaper. On Ryoku the desktop already turns it into a full palette, so use that.
    ryoku = read_json(RYOKU_PALETTE) or {}
    if ryoku.get("background") and ryoku.get("primary"):
        theme = dict(FALLBACK)
        theme.update({k: v for k, v in ryoku.items() if valid(v)})
        theme["dark"] = luminance(theme["background"]) < 0.5
        return theme
    return from_wallpaper() or dict(FALLBACK)
