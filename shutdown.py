"""Shutdown coordination: a system-sleep watchdog and a shared idle flag.

Two independent mechanisms feed the app's single exit:

1. Sleep watchdog — a daemon thread that detects the machine going to sleep
   (laptop lid closed). On wake the VISA sessions to the instruments are stale,
   so there is nothing worth cleaning up: it hard-exits via fast_exit, skipping
   close_inst (whose check_inst queries would hang on a dead session). The OS
   reclaims the USB/VISA session.

2. Idle flag — set by the plot window when it times out on inactivity. The
   plot's normal close loops back to the config window, so main.py checks this
   flag after the plot to break the loop instead. (The config window needs no
   flag: its idle close already returns None, which breaks the loop.)
"""

import ctypes
import logging
import threading
import time

from logger import fast_exit

log = logging.getLogger(__name__)

# Windows-only app. QueryUnbiasedInterruptTime returns system uptime EXCLUDING
# time spent asleep or hibernating (100 ns units). We do not use time.monotonic()
# here: on Windows it is QueryPerformanceCounter(), whose behavior across sleep is
# hardware/firmware-dependent (halts on some machines, keeps counting on TSC-based
# ones and in Modern Standby). QueryUnbiasedInterruptTime is contractually defined
# to exclude sleep on all hardware, which is exactly the signal we need.
_kernel32 = ctypes.windll.kernel32


def _sleep_free_clock():
    """Seconds of system uptime, excluding time spent asleep/hibernating."""
    t = ctypes.c_ulonglong()
    _kernel32.QueryUnbiasedInterruptTime(ctypes.byref(t))
    return t.value / 1e7   # 100 ns units -> seconds


# We detect system sleep (laptop lid closed) by comparing the wall clock — which
# keeps advancing across sleep — against _sleep_free_clock(), which stops during
# sleep. Over one tick their divergence is the time spent asleep; anything past
# SLEEP_THRESHOLD_S means the machine slept (rather than the thread merely being
# busy) and the VISA sessions are now stale.
SLEEP_THRESHOLD_S = 30
_WATCHDOG_TICK_S = 2

# Idle timeout shared by the config and plot windows: auto-close after this long
# with no mouse/keyboard activity so an abandoned session releases the
# instruments. IDLE_MS is the same duration for the plot's browser-side check;
# IDLE_POLL_MS is how often each window re-checks.
IDLE_SECONDS = 30
IDLE_MS = IDLE_SECONDS * 1000
IDLE_POLL_MS = 10000

_idle_shutdown = threading.Event()


def request():
    """Ask main.py to end the run loop (used by the plot window's idle timeout)."""
    _idle_shutdown.set()


def requested():
    """True once request() has been called."""
    return _idle_shutdown.is_set()


def start_sleep_watchdog():
    """Launch a daemon thread that hard-exits the process on system sleep.

    Runs even while the main thread is blocked in Tk's mainloop() or pywebview's
    start(), because those release the GIL during their native event loops.
    """
    def _watch():
        last_wall = time.time()
        last_free = _sleep_free_clock()
        while True:
            time.sleep(_WATCHDOG_TICK_S)
            now_wall = time.time()
            now_free = _sleep_free_clock()
            if (now_wall - last_wall) - (now_free - last_free) > SLEEP_THRESHOLD_S:
                log.warning(
                    "System sleep detected — instrument sessions are stale, exiting.")
                fast_exit(0)
            last_wall = now_wall
            last_free = now_free

    threading.Thread(target=_watch, name="sleep-watchdog", daemon=True).start()
