"""Write cornerplay/sounds/ambient.ogg: TV mode's calm background loop.

An original piece, made here from sine waves (no samples, no one else's music): four slow
chords on a soft pad, a few bell notes from a pentatonic scale, and a gentle echo. Every note
that runs past the end wraps round to the start, so the loop has no seam.
    python3 packaging/make-ambient.py      (needs numpy and ffmpeg)
"""
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

RATE = 44100
BAR = 8.0                      # seconds per chord
CHORDS = [  # semitones from A2 (110 Hz): Fmaj7, G6, Em7, Am9 -- warm, unresolved, unhurried
    [-4, 8, 12, 15, 19],
    [-2, 10, 14, 17, 21],
    [-5, 7, 14, 17, 19],
    [0, 12, 15, 19, 23],
]
SCALE = [0, 3, 5, 7, 10, 12, 15, 17, 19, 22, 24]  # A minor pentatonic, two octaves up from A4
LENGTH = int(RATE * BAR * len(CHORDS) * 2)         # the progression twice: 64 s


def hz(semi, base=110.0):
    return base * 2 ** (semi / 12)


def add(buf, start, sig):
    """Add sig into buf from start, wrapping past the end (a seamless loop)."""
    n = len(sig)
    i = start % len(buf)
    first = min(n, len(buf) - i)
    buf[i:i + first] += sig[:first]
    if first < n:
        add(buf, 0, sig[first:])


def pad(freq, dur, rng):
    t = np.arange(int(dur * RATE)) / RATE
    env = np.minimum(1, t / 2.5) * np.minimum(1, (dur - t) / 3.0).clip(0)  # slow swell in and out
    sig = np.zeros_like(t)
    for detune, amp in ((-0.08, 0.5), (0.0, 1.0), (0.07, 0.5)):
        sig += amp * np.sin(2 * np.pi * (freq + detune) * t + rng.uniform(0, 6.28))
    sig += 0.12 * np.sin(2 * np.pi * freq * 2 * t)                       # a little air
    return sig * env * (0.5 + 0.5 * np.sin(2 * np.pi * 0.07 * t + rng.uniform(0, 6.28)) * 0.3)


def bell(freq, rng):
    dur = 4.5
    t = np.arange(int(dur * RATE)) / RATE
    env = np.exp(-t * 1.1) * np.minimum(1, t / 0.01)
    sig = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * freq * 2.76 * t) * np.exp(-t * 2.5)
    return sig * env


def main(out):
    rng = np.random.default_rng(7)
    left, right = np.zeros(LENGTH), np.zeros(LENGTH)
    bars = int(LENGTH / RATE / BAR)
    for b in range(bars):
        chord = CHORDS[b % len(CHORDS)]
        start = int(b * BAR * RATE)
        for k, semi in enumerate(chord):
            s = pad(hz(semi), BAR + 3.5, rng) * (0.22 if k == 0 else 0.11)
            pan = 0.5 + (k - 2) * 0.12
            add(left, start, s * (1 - pan) * 2)
            add(right, start, s * pan * 2)
        for _ in range(rng.integers(1, 4)):  # a few bell notes per chord, never on a fixed beat
            when = start + int(rng.uniform(0.5, BAR - 1.0) * RATE)
            s = bell(hz(rng.choice(SCALE), 440.0), rng) * rng.uniform(0.05, 0.09)
            pan = rng.uniform(0.25, 0.75)
            add(left, when, s * (1 - pan) * 2)
            add(right, when, s * pan * 2)
    # A soft echo, worked out round the loop twice so the tail carries over the seam.
    for ch, delay in ((left, int(0.43 * RATE)), (right, int(0.57 * RATE))):
        wet = np.zeros(LENGTH)
        for _ in range(2):
            wet = 0.42 * np.roll(ch + wet, delay)
        ch += 0.6 * wet
    # A gentle low-pass, done on the spectrum: the loop is circular, so the filter wraps too.
    f = np.fft.rfftfreq(LENGTH, 1 / RATE)
    soften = 1 / np.sqrt(1 + (f / 2600.0) ** 4)
    left = np.fft.irfft(np.fft.rfft(left) * soften, LENGTH)
    right = np.fft.irfft(np.fft.rfft(right) * soften, LENGTH)
    peak = max(np.abs(left).max(), np.abs(right).max())
    stereo = np.stack([left, right], axis=1) / peak * 0.5
    pcm = (stereo * 32767).astype("<i2")
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "ambient.wav"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(pcm.tobytes())
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-c:a", "libvorbis", "-q:a", "3", str(out)],
                       check=True)
    print(f"wrote {out} ({Path(out).stat().st_size // 1024} KiB, {LENGTH / RATE:.0f} s)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parent.parent / "cornerplay/sounds/ambient.ogg"))
