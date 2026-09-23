"""Resolve the base directory for data files from a `data_dir.txt` file.

The file lives next to the scripts and holds a single directory path (one line,
`~` allowed). It acts like a local environment variable pointing at where presets
and results live. When it is missing, empty, or unreadable we fall back to the
directory containing the scripts, preserving the original "next to the code"
behaviour so nothing breaks without it.

The file is read once, on the first call, and the result is reused for the rest
of the run. Nothing is logged here: the first call happens before logging is set
up (setup_logging needs the data directory to place its log file), so
setup_logging reports the result instead.
"""
import functools
import sys

from pathlib import Path

# Anchor next to the running program. As a frozen PyInstaller exe, __file__
# points inside the bundle (_internal), so use the executable's own directory;
# as a normal script, use the directory containing this module.
if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys.executable).resolve().parent
else:
    _BASE_DIR = Path(__file__).resolve().parent

_DATAPATH_FILE = _BASE_DIR / "data_dir.txt"


@functools.cache
def _resolve():
    """Return (directory, fallback_reason). The reason is None when the
    directory came from `data_dir.txt`."""
    try:
        text = _DATAPATH_FILE.read_text()
    except OSError:
        return _BASE_DIR, f"{_DATAPATH_FILE} cannot be read"
    for line in text.splitlines():
        line = line.strip()
        if line:
            dir_path = Path(line.replace("\\", "/")).expanduser()
            try:
                dir_path.mkdir(parents=False, exist_ok=True)
            except OSError:
                return _BASE_DIR, f"cannot create {dir_path} (does {dir_path.parent} exist?)"
            return dir_path, None
    return _BASE_DIR, f"{_DATAPATH_FILE} is empty"


def data_dir():
    """Return the configured base data directory as a Path.

    Reads the first non-blank line of `data_dir.txt` and expands a leading `~`.
    Falls back to the directory containing this module on any failure.
    """
    return _resolve()[0]


def data_dir_fallback_reason():
    """Why data_dir() fell back to the program folder, or None if it didn't."""
    return _resolve()[1]


def data_path(*parts, mkdir=True):
    """Join path `parts` onto the base data directory (see data_dir())."""
    ret_path = data_dir().joinpath(*parts)
    if mkdir:
        ret_path.mkdir(parents=False, exist_ok=True)
    return ret_path

if __name__ == "__main__":
    print(data_dir(), data_dir_fallback_reason() or "")
