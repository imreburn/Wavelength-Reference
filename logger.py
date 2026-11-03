import logging
import os
import sys
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from datapath import data_path, data_dir, data_dir_fallback_reason


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
    """Configure logging once. Writes to logs/<app_name>/<date>_<time>.log (a new file per run) and the console. `app_name` keeps each program's logs in their own folder and tags every line via the %(name)s field.

    `max_files` caps how many run logs are kept in the folder: the oldest are
    deleted at startup so at most `max_files` remain. `max_bytes` caps the size
    of each run's file; if a run exceeds it the file is truncated and reused, so
    no extra backup files accumulate."""
    log_dir = data_path("logs") / app_name
    log_dir.mkdir(parents=True, exist_ok=True)

    # Prune old runs (oldest first) so this run brings the total to max_files.
    existing = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime)
    keep = max(max_files - 1, 0)
    for old in existing[:max(len(existing) - keep, 0)]:
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

    # datapath resolves the data directory silently (it runs before this
    # function configures logging), so report it here, once per run.
    reason = data_dir_fallback_reason()
    if reason:
        logging.getLogger(app_name).warning(
            "Data directory: %s (default; %s)", data_dir(), reason)
    else:
        logging.getLogger(app_name).info(
            "Data directory: %s (from data_dir.txt)", data_dir())

    # An exception that escapes a non-main thread's target (e.g. the werkzeug
    # serve_forever loop outside a request, or any library-spawned thread) is
    # sent to threading.excepthook, which by default only prints to stderr — so
    # it reaches the console but not the log file. Route it through logging so it
    # lands in both. NOTE: this only catches exceptions that fully escape a
    # thread; errors swallowed inside a framework's own event loop
    # (Tk callbacks, Dash callbacks) never get here and still need their own
    # handlers.
    def _log_thread_exception(args):
        if args.exc_type is SystemExit:
            return
        logging.getLogger(app_name).error(
            "Uncaught exception in thread %s",
            args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = _log_thread_exception

    # An exception raised where Python can't propagate it (e.g. in a __del__
    # run by the garbage collector) goes to sys.unraisablehook, which by
    # default also prints only to stderr ("Exception ignored while ..."). Log
    # it with the thread it happened on, since a finalizer runs on whichever
    # thread triggered the collection.
    def _log_unraisable(args):
        msg = args.err_msg or "Exception ignored in"
        if args.object is not None:
            msg = f"{msg}: {args.object!r}"
        logging.getLogger(app_name).error(
            "%s (thread %s)", msg, threading.current_thread().name,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.unraisablehook = _log_unraisable

    # An exception that escapes the main program ends it, and in the packaged
    # .exe the console window closes along with it, before anyone can read the
    # error (#127). Log it here, and in the .exe keep the window open until
    # the user closes it. Python calls this hook only after every `finally`
    # on the way out has run, so main.py has already turned the laser off and
    # closed the instruments: the open window holds nothing.
    def _log_uncaught(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            # Ctrl+C means "quit", not an error: no message and no wait.
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.getLogger(app_name).error(
            "Unhandled error", exc_info=(exc_type, exc_value, exc_tb))
        if getattr(sys, "frozen", False):
            bar = "=" * 60
            print(f"\n{bar}\n"
                  " The program stopped because of an error. The log is saved to:\n"
                  f"   {log_file}\n"
                  " Close this window, then restart the program.\n"
                  f"{bar}", flush=True)
            # Sleep rather than input(): an Enter typed into the console
            # earlier is still in its input buffer, and input() would read it
            # and close the window at once. Closing the window ends the
            # process; Ctrl+C (not mentioned to users) ends the wait quietly.
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        fast_exit(1)

    sys.excepthook = _log_uncaught

    return logging.getLogger(app_name)
