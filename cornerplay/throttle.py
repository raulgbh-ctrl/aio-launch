"""A download speed limit for tools that have none (legendary, gogdl, nile).

The tool's processes are frozen (SIGSTOP) for part of every short cycle and let go again
(SIGCONT): running a quarter of the time gives about a quarter of the speed. How much of each
cycle it runs is steered by the speed the tool itself reports ("+ Download - 12.3 MiB/s"),
which already counts the frozen moments. Network connections survive pauses this short.
"""
import os
import signal

from PySide6.QtCore import QObject, QTimer

PERIOD_MS = 500
MIN_SHARE = 0.03


def tree(pid: int) -> list:
    """pid and all its descendants (from /proc's children lists)."""
    out, todo = [], [pid]
    while todo:
        p = todo.pop()
        out.append(p)
        try:
            for task in os.listdir(f"/proc/{p}/task"):
                with open(f"/proc/{p}/task/{task}/children") as f:
                    todo += [int(c) for c in f.read().split()]
        except (OSError, ValueError):
            pass
    return out


def _signal(pids, sig):
    for p in pids:
        try:
            os.kill(p, sig)
        except OSError:
            pass


class Throttle(QObject):
    """Keeps one process tree's download speed under limit() bytes per second (0 = no limit)."""

    def __init__(self, pid, limit, parent=None):
        super().__init__(parent)
        self.pid, self.limit = pid, limit
        self.share = 1.0  # of each cycle the tool runs
        self.frozen = False
        self.timer = QTimer(self, singleShot=True)
        self.timer.timeout.connect(self._tick)
        self.timer.start(PERIOD_MS)

    def reported(self, speed):
        """The tool said how fast it went (bytes per second): steer the share towards the limit."""
        limit = self.limit()
        if not limit or speed <= 0:
            return
        wanted = self.share * limit / speed
        # Halfway there each time: a smooth approach instead of a swing.
        self.share = min(1.0, max(MIN_SHARE, (self.share * wanted) ** 0.5))

    def _tick(self):
        limit = self.limit()
        if not limit or self.share >= 0.999:
            if self.frozen:
                self._thaw()
            self.timer.start(PERIOD_MS)
            return
        if self.frozen:
            self._thaw()
            self.timer.start(max(20, int(PERIOD_MS * self.share)))
        else:
            _signal(tree(self.pid), signal.SIGSTOP)
            self.frozen = True
            self.timer.start(max(20, int(PERIOD_MS * (1 - self.share))))

    def _thaw(self):
        _signal(tree(self.pid), signal.SIGCONT)
        self.frozen = False

    def stop(self):
        """Never leave the tool frozen: before ending or terminating it, let it go."""
        self.timer.stop()
        if self.frozen:
            self._thaw()
