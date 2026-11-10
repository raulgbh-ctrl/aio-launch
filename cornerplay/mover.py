"""Move a game's folder to another place, printing "Progress: NN.N" for the app's progress strip.

    python -m cornerplay.mover SOURCE DEST

The same drive: an instant rename. Another drive: copy everything (keeping links and
times), then delete the original; if the copy fails, the half-copied folder is removed
and the original is left as it was.
"""
import os
import shutil
import signal
import sys


def main(src, dst):
    src, dst = os.path.realpath(src), os.path.abspath(dst)
    if not os.path.isdir(src):
        sys.exit(f"error: {src} is not a folder")
    if os.path.exists(dst):
        sys.exit(f"error: {dst} already exists")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.rename(src, dst)  # same filesystem
        print("Progress: 100.0", flush=True)
        return
    except OSError:
        pass
    total = sum(os.lstat(os.path.join(r, f)).st_size for r, _d, fs in os.walk(src) for f in fs) or 1
    done, last = 0, -1.0
    try:
        for root, dirs, files in os.walk(src):
            rel = os.path.relpath(root, src)
            target = os.path.join(dst, rel) if rel != "." else dst
            os.makedirs(target, exist_ok=True)
            for d in dirs:  # links to folders are copied as links
                s = os.path.join(root, d)
                if os.path.islink(s):
                    os.symlink(os.readlink(s), os.path.join(target, d))
            for f in files:
                s, t = os.path.join(root, f), os.path.join(target, f)
                if os.path.islink(s):
                    os.symlink(os.readlink(s), t)
                    continue
                shutil.copy2(s, t)
                done += os.lstat(s).st_size
                pct = round(done * 100 / total, 1)
                if pct - last >= 0.5:
                    print(f"Progress: {pct}", flush=True)
                    last = pct
    except (OSError, KeyboardInterrupt) as e:
        shutil.rmtree(dst, ignore_errors=True)
        sys.exit(f"error: copy failed ({e}); nothing was moved")
    shutil.rmtree(src)
    print("Progress: 100.0", flush=True)


if __name__ == "__main__":
    # Cancel (SIGTERM from the app) cleans up like a failed copy.
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    if len(sys.argv) != 3:
        sys.exit("usage: python -m cornerplay.mover SOURCE DEST")
    main(sys.argv[1], sys.argv[2])
