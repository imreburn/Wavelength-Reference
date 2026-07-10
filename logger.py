import logging
import os
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from datapath import data_path


def fast_exit(code=0):
    """Terminate the process immediately, skipping the slow native teardown.

    pywebview's WebView2/.NET runtime takes a couple of seconds to finalize
    after the interpreter's atexit handlers run, so the console window lingers
    well after the last GUI window closes. Once all real work is done there is
    nothing left worth waiting for, so flush the logs by hand (os._exit does
    not run atexit/logging.shutdown) and hard-exit. Call this only at true
    program end, after instruments are closed."""
    logging.shutdown()
    os._exit(code)

def setup_logging(app_name, level=logging.INFO, max_files=20, max_bytes=10 * 1024 * 1024):
    """Configure logging once. Writes to logs/<app_name>/<date>_<time>.log (a new
    file per run) and the console. `app_name` keeps each program's logs in their
    own folder and tags every line via the %(name)s field.

    `max_files` caps how many run logs are kept in the folder: the oldest are
    deleted at startup so at most `max_files` remain. `max_bytes` caps the size
    of each run's file; if a run exceeds it the file is truncated and reused, so
    no extra backup files accumulate."""
    log_dir = data_path("logs") / app_name
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
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    # An exception that escapes a non-main thread's target (e.g. the werkzeug
    # serve_forever loop outside a request, or any library-spawned thread) is
    # sent to threading.excepthook, which by default only prints to stderr — so
    # it reaches the console but not the log file. Route it through logging so it
    # lands in both. NOTE: this only catches exceptions that fully escape a
    # thread; errors swallowed inside a framework's own event loop (Tk callbacks,
    # Dash callbacks) never get here and still need their own handlers.
    def _log_thread_exception(args):
        if args.exc_type is SystemExit:
            return
        logging.getLogger(app_name).error(
            "Uncaught exception in thread %s",
            args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = _log_thread_exception

    return logging.getLogger(app_name)
