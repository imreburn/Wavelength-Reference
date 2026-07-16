"""Resolve the base directory for data files from a `data_dir.txt` file.

The file lives next to the scripts and holds a single directory path (one line,
`~` allowed). It acts like a local environment variable pointing at where presets
and results live. When it is missing, empty, or unreadable we fall back to the
directory containing the scripts, preserving the original "next to the code"
behaviour so nothing breaks without it.
"""
import sys

from pathlib import Path
import logging

log = logging.getLogger(__name__)
# Anchor next to the running program. As a frozen PyInstaller exe, __file__
# points inside the bundle (_internal), so use the executable's own directory;
# as a normal script, use the directory containing this module.
if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys.executable).resolve().parent
else:
    _BASE_DIR = Path(__file__).resolve().parent

_DATAPATH_FILE = _BASE_DIR / "data_dir.txt"


def data_dir():
    """Return the configured base data directory as a Path.

    Reads the first non-blank line of `data_dir.txt` and expands a leading `~`.
    Falls back to the directory containing this module on any failure.
    """
    log.info("Read a path from data_dir.txt: %s", str(_DATAPATH_FILE))
    try:
        for line in _DATAPATH_FILE.read_text().splitlines():
            line = line.strip()
            if line:
                dir_path = Path(line.replace("\\", "/")).expanduser()
                dir_path.mkdir(parents=False, exist_ok=True)
                log.info("Successful. Path: %s", str(dir_path))
                return dir_path
    except OSError:
        pass
    log.info("data_dir.txt cannot be read or %s does not exist. Use the default path: %s", str(dir_path.parent), str(_DATAPATH_FILE.parent))
    return _DATAPATH_FILE.parent


def data_path(*parts, mkdir=True):
    """Join path `parts` onto the base data directory (see data_dir())."""
    ret_path = data_dir().joinpath(*parts)
    if mkdir:
        ret_path.mkdir(parents=False, exist_ok=True)
    return ret_path

if __name__ == "__main__":
    data_dir()