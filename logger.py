import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(app_name, level=logging.INFO, max_files=20, max_bytes=10 * 1024 * 1024):
    """Configure logging once. Writes to logs/<app_name>/<date>_<time>.log (a new
    file per run) and the console. `app_name` keeps each program's logs in their
    own folder and tags every line via the %(name)s field.

    `max_files` caps how many run logs are kept in the folder: the oldest are
    deleted at startup so at most `max_files` remain. `max_bytes` caps the size
    of each run's file; if a run exceeds it the file is truncated and reused, so
    no extra backup files accumulate."""
    log_dir = Path("logs") / app_name
    log_dir.mkdir(parents=True, exist_ok=True)

    # Prune old runs (oldest first) so this run brings the total to max_files.
    existing = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime)
    keep = max(max_files - 1, 0)
    for old in existing[:len(existing) - keep]:
        old.unlink()

    log_file = log_dir / f"{datetime.now():%Y-%m-%d_%H-%M-%S}.log"

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            RotatingFileHandler(
                log_file, maxBytes=max_bytes, backupCount=0, encoding="utf-8"
            ),
            logging.StreamHandler(),
        ],
    )

    # Werkzeug's dev server logs one INFO line per HTTP request (static assets,
    # callbacks, etc.). Quiet it to WARNING so only real problems (4xx/5xx) show.
    # logging.getLogger("werkzeug").setLevel(logging.WARNING)

    return logging.getLogger(app_name)
