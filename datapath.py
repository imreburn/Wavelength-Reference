"""Resolve the base directory for data files from a `.datapath` dotfile.

The dotfile lives next to the scripts and holds a single directory path (one line,
`~` allowed). It acts like a local environment variable pointing at where presets
and results live. When it is missing, empty, or unreadable we fall back to the
directory containing the scripts, preserving the original "next to the code"
behaviour so nothing breaks without it.
"""
import logging

log = logging.getLogger(__name__)

from pathlib import Path

_DOTFILE = Path(__file__).resolve().parent / ".datapath"


def data_dir():
    """Return the configured base data directory as a Path.

    Reads the first non-blank line of `.datapath` and expands a leading `~`.
    Falls back to the directory containing this module on any failure.
    """
    try:
        for line in _DOTFILE.read_text().splitlines():
            line = line.strip()
            if line:
                return Path(line.replace("\\", "/")).expanduser()
    except OSError:
        pass
    return _DOTFILE.parent


def data_path(*parts):
    """Join path `parts` onto the base data directory (see data_dir())."""
    return data_dir().joinpath(*parts)
