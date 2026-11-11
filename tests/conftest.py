"""Every test runs against a throwaway home: cornerplay.config creates its folders on import,
so HOME and the XDG folders are pointed at a temp dir before anything imports it."""
import os
import sys
import tempfile
from pathlib import Path

_HOME = Path(tempfile.mkdtemp(prefix="cornerplay-test-home-"))
os.environ["HOME"] = str(_HOME)
for var, sub in (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"), ("XDG_CACHE_HOME", ".cache")):
    os.environ[var] = str(_HOME / sub)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
