"""Resolve the base directory for data files from a `datapath.txt` file.

The file lives next to the scripts and holds a single directory path (one line,
`~` allowed). It acts like a local environment variable pointing at where presets
and results live. When it is missing, empty, or unreadable we fall back to the
directory containing the scripts, preserving the original "next to the code"
behaviour so nothing breaks without it.
"""
import sys
from pathlib import Path

# Anchor next to the running program. As a frozen PyInstaller exe, __file__
# points inside the bundle (_internal), so use the executable's own directory;
# as a normal script, use the directory containing this module.
if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys.executable).resolve().parent
else:
    _BASE_DIR = Path(__file__).resolve().parent

_DATAPATH_FILE = _BASE_DIR / "datapath.txt"


def data_dir():
    """Return the configured base data directory as a Path.

    Reads the first non-blank line of `datapath.txt` and expands a leading `~`.
    Falls back to the directory containing this module on any failure.
    """
    try:
        for line in _DATAPATH_FILE.read_text().splitlines():
            line = line.strip()
            if line:
                return Path(line.replace("\\", "/")).expanduser()
    except OSError:
        pass
    return _DATAPATH_FILE.parent


def data_path(*parts):
    """Join path `parts` onto the base data directory (see data_dir())."""
    return data_dir().joinpath(*parts)
