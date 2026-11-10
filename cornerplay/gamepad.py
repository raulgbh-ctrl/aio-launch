"""Controller input through SDL2, turned into key presses for the focused Cornerplay window.

Mapping: D-pad / left stick = arrows, A = Return, B = Escape, X = F2 (actions),
Y = F3 (installed only), LB / RB = PageUp / PageDown (previous / next store),
Start = F11 (TV mode). Nothing is sent while Cornerplay is not the focused window,
so the pad never steers the library while a game is running.
"""
import ctypes
import ctypes.util
import time

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Property, Signal
from PySide6.QtGui import QGuiApplication, QKeyEvent

INIT_GAMECONTROLLER = 0x00002000
DEVICE_ADDED, DEVICE_REMOVED = 0x653, 0x654
AXIS_MOTION, BUTTON_DOWN, BUTTON_UP = 0x650, 0x651, 0x652

BUTTONS = {
    0: Qt.Key_Return, 1: Qt.Key_Escape, 2: Qt.Key_F2, 3: Qt.Key_F3,
    6: Qt.Key_F11, 9: Qt.Key_PageUp, 10: Qt.Key_PageDown,
    11: Qt.Key_Up, 12: Qt.Key_Down, 13: Qt.Key_Left, 14: Qt.Key_Right,
}
REPEATING = {Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right}
# SDL_GameControllerType -> which button glyphs to show. Unknown pads (and the Steam Deck,
# which Steam presents as an Xbox pad) get Xbox glyphs.
STYLES = {3: "playstation", 4: "playstation", 7: "playstation",
          5: "nintendo", 11: "nintendo", 12: "nintendo", 13: "nintendo"}
STICK_ON, STICK_OFF = 18000, 12000
ACTIVE_MS, IDLE_MS = 16, 1000  # 60 checks a second while in use, one a second otherwise
FIRST_REPEAT = 0.38
# Holding a direction speeds up: (held for at least, seconds between moves).
REPEAT_STEPS = ((0.0, 0.11), (1.0, 0.06), (2.0, 0.035))
# The triggers (axes 4 and 5: LT / RT, L2 / R2) page through a row: Shift+Left / Shift+Right.
TRIGGERS = {4: Qt.Key_Left, 5: Qt.Key_Right}
TRIGGER_ON, TRIGGER_OFF = 16000, 8000
PAGE = Qt.ShiftModifier


def _repeat_gap(held_for):
    gap = REPEAT_STEPS[0][1]
    for after, step in REPEAT_STEPS:
        if held_for >= after:
            gap = step
    return gap


START_DELAY_MS = 300  # SDL_Init scans every input device (~150 ms); do it after the window is up


class Gamepad(QObject):
    connectedChanged = Signal()
    availableChanged = Signal()
    styleChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sdl = None
        self._pads = {}    # instance id -> controller handle
        self._held = {}    # Qt key -> time of next repeat
        self._stick = {}   # (pad, axis) -> key currently held by that stick axis
        self._event = ctypes.create_string_buffer(128)
        self._timer = None
        self._style = "xbox"
        self._deck = self._is_deck()
        QTimer.singleShot(START_DELAY_MS, self._start)

    def _start(self):
        try:
            self._load()
        except (OSError, AttributeError):
            self._sdl = None
            return
        self.availableChanged.emit()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(IDLE_MS)
        QGuiApplication.instance().focusWindowChanged.connect(lambda _w: self._pace())
        self._poll()  # pick up controllers that were plugged in before we started

    def _pace(self):
        """Fast polling only while a controller is plugged in and this app has focus."""
        fast = bool(self._pads) and QGuiApplication.focusWindow() is not None
        interval = ACTIVE_MS if fast else IDLE_MS
        if self._timer.interval() != interval:
            self._timer.setInterval(interval)

    def _load(self):
        try:
            sdl = ctypes.CDLL("libSDL2-2.0.so.0")  # direct load; find_library runs ldconfig (~25 ms)
        except OSError:
            sdl = ctypes.CDLL(ctypes.util.find_library("SDL2") or "libSDL2.so")
        sdl.SDL_SetHint.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        sdl.SDL_Init.argtypes = [ctypes.c_uint32]
        sdl.SDL_PollEvent.argtypes = [ctypes.c_void_p]
        sdl.SDL_GameControllerOpen.argtypes = [ctypes.c_int]
        sdl.SDL_GameControllerOpen.restype = ctypes.c_void_p
        sdl.SDL_GameControllerGetJoystick.argtypes = [ctypes.c_void_p]
        sdl.SDL_GameControllerGetJoystick.restype = ctypes.c_void_p
        sdl.SDL_JoystickInstanceID.argtypes = [ctypes.c_void_p]
        sdl.SDL_JoystickInstanceID.restype = ctypes.c_int32
        sdl.SDL_GameControllerClose.argtypes = [ctypes.c_void_p]
        try:  # SDL 2.0.12 and newer
            sdl.SDL_GameControllerGetType.argtypes = [ctypes.c_void_p]
            sdl.SDL_GameControllerGetType.restype = ctypes.c_int
            self._get_type = sdl.SDL_GameControllerGetType
        except AttributeError:
            self._get_type = None
        sdl.SDL_SetHint(b"SDL_NO_SIGNAL_HANDLERS", b"1")
        sdl.SDL_SetHint(b"SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", b"1")
        if sdl.SDL_Init(INIT_GAMECONTROLLER) != 0:
            raise OSError("SDL_Init failed")
        self._sdl = sdl

    @staticmethod
    def _is_deck():
        """Steam Deck hardware. In Desktop Mode Steam turns its controller into a keyboard
        (A = Enter, B = Esc, Y = Space, D-pad = arrows), so SDL never sees a pad there."""
        try:
            vendor = open("/sys/class/dmi/id/board_vendor").read().strip()
            product = open("/sys/class/dmi/id/product_name").read().strip()
        except OSError:
            return False
        return vendor == "Valve" and product in ("Jupiter", "Galileo")

    available = Property(bool, lambda s: s._sdl is not None, notify=availableChanged)
    deck = Property(bool, lambda s: s._deck, constant=True)
    connected = Property(bool, lambda s: bool(s._pads), notify=connectedChanged)
    style = Property(str, lambda s: s._style, notify=styleChanged)  # "xbox", "playstation" or "nintendo"

    # --- SDL events ------------------------------------------------------
    def _poll(self):
        sdl, ev = self._sdl, self._event
        while sdl.SDL_PollEvent(ev):
            kind = ctypes.c_uint32.from_buffer(ev, 0).value
            which = ctypes.c_int32.from_buffer(ev, 8).value
            if kind == DEVICE_ADDED:
                handle = sdl.SDL_GameControllerOpen(which)
                if handle:
                    iid = sdl.SDL_JoystickInstanceID(sdl.SDL_GameControllerGetJoystick(handle))
                    self._pads[iid] = handle
                    if self._get_type:  # the pad plugged in last decides the glyphs
                        style = STYLES.get(self._get_type(handle), "xbox")
                        if style != self._style:
                            self._style = style
                            self.styleChanged.emit()
                    self.connectedChanged.emit()
                    self._pace()
            elif kind == DEVICE_REMOVED:
                handle = self._pads.pop(which, None)
                if handle:
                    sdl.SDL_GameControllerClose(handle)
                    self.connectedChanged.emit()
                    self._pace()
                self._held.clear()
                self._stick.clear()
            elif kind in (BUTTON_DOWN, BUTTON_UP):
                key = BUTTONS.get(ev.raw[12])
                if key is not None:
                    self._set(key, kind == BUTTON_DOWN)
            elif kind == AXIS_MOTION:
                axis = ev.raw[12]
                value = ctypes.c_int16.from_buffer(ev, 16).value
                if axis in (0, 1):
                    self._axis(which, axis, value)
                elif axis in TRIGGERS:
                    self._trigger(which, axis, value)
        now = time.monotonic()
        for held, (due, since) in list(self._held.items()):
            if now >= due:
                self._held[held] = (now + _repeat_gap(now - since), since)
                self._send(*held, repeat=True)

    def _axis(self, pad, axis, value):
        low, high = (Qt.Key_Left, Qt.Key_Right) if axis == 0 else (Qt.Key_Up, Qt.Key_Down)
        current = self._stick.get((pad, axis))
        wanted = current
        if abs(value) < STICK_OFF:
            wanted = None
        elif value <= -STICK_ON:
            wanted = low
        elif value >= STICK_ON:
            wanted = high
        if wanted != current:
            if current is not None:
                self._set(current, False)
            if wanted is not None:
                self._set(wanted, True)
            self._stick[(pad, axis)] = wanted

    def _trigger(self, pad, axis, value):
        on = self._stick.get((pad, axis))
        if not on and value >= TRIGGER_ON:
            self._stick[(pad, axis)] = True
            self._set(TRIGGERS[axis], True, PAGE)
        elif on and value <= TRIGGER_OFF:
            self._stick[(pad, axis)] = False
            self._set(TRIGGERS[axis], False, PAGE)

    def _set(self, key, down, mods=Qt.NoModifier):
        held = (key, mods)
        if not down:
            self._held.pop(held, None)
            return
        if key in REPEATING:
            now = time.monotonic()
            self._held[held] = (now + FIRST_REPEAT, now)
        self._send(key, mods)

    def _send(self, key, mods=Qt.NoModifier, repeat=False):
        window = QGuiApplication.focusWindow()
        if window is None:  # a game (or anything else) has focus: stay out of the way
            self._held.clear()
            return
        for kind in (QEvent.KeyPress, QEvent.KeyRelease):
            QGuiApplication.postEvent(window, QKeyEvent(kind, key, mods, "", repeat))
