"""inst_run_ext.py - Sweep with an external laser the program does not control.

The power meter is armed exactly as in TLS mode (arm_pm), but the sweep — and
the trigger that starts the log — comes from a laser the user drives by hand.
So instead of commanding the laser and polling its sweep state, this module
prints setup instructions to the console and polls the power meter until the
log completes, or the user cancels.

Everything power-meter-side is imported from inst_run; only the wait and the
cancel path live here.
"""
import time
import logging

from inst_helper import prep_inst, check_inst
from inst_run import arm_pm, disarm_pm, logging_complete, read_pm, SweepCancelled
from structs import Params
import shutdown

try:
    import msvcrt   # Windows: non-blocking key reads for Esc-to-cancel
except ImportError:
    msvcrt = None   # Mac dev machine: Ctrl+C is the only cancel key

log = logging.getLogger(__name__)

# Number of times run_sweep_ext has been called since this module was imported
# (i.e. since main.py started). Separate from inst_run's counter: the laser
# source is chosen at startup and can't change without a restart, so only one
# of the two ever runs in a process.
_sweep_count = 0

ESC = "\x1b"


def _print_instructions(params : Params, scan_label=""):
    """Console prompt shown while the PM is armed, waiting for the external laser.
    """
    duration = params.num_data * params.at_us / 1e6   # s

    title = " EXTERNAL LASER"
    if scan_label:
        title += f"  -  {scan_label}"
    bar = "=" * 60

    print()
    print(bar)
    print(title)
    print(f" Power meter is armed (range {params.pm_range} dBm).")
    print(" Start the sweep on the external laser.")
    print()
    print(f"   Start wavelength  : {params.wl_st_pad:.3f} nm")
    print(f"   Stop wavelength   : {params.wl_sp_pad:.3f} nm")
    print(f"   Sweep speed       : {params.speed:g} nm/s")
    print(f"   Expected duration : {duration:.1f} s")
    print()
    print(" To cancel, click this window and press Esc (or Ctrl+C).")
    print(bar)


def _flush_keys():
    """Discard key presses buffered before the wait began, so an Esc pressed
    during an earlier run cannot cancel this one."""
    while msvcrt and msvcrt.kbhit():
        msvcrt.getwch()


def _esc_pressed():
    """Non-blocking: True if Esc is among the keys pressed since the last call."""
    while msvcrt and msvcrt.kbhit():
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):   # arrow/function key: two-char code, skip both
            msvcrt.getwch()
            continue
        if ch == ESC:
            return True
    return False


def wait_for_sweep(pm, params : Params):
    """Block until every channel's log completes.

    Returns False if the user cancels (Esc in the console, or Ctrl+C) or if
    nothing arrives within IDLE_SECONDS. The console can't see the key presses
    that would reset an idle deadline, so this is simply a maximum armed time;
    on expiry shutdown.request() is set so main.py exits instead of reopening
    the config window.
    """
    _flush_keys()
    start = time.time()
    try:
        while not logging_complete(pm, params):
            if _esc_pressed():
                print()
                log.info("[PM] Cancelled by user (Esc)")
                return False
            elapsed = time.time() - start
            if elapsed >= shutdown.IDLE_SECONDS:
                print()
                log.info("Idle timeout while armed — closing.")
                shutdown.request()
                return False
            print(f"\r  Waiting... {int(elapsed)} s", end="", flush=True)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print()
        log.info("[PM] Cancelled by user (Ctrl+C)")
        return False
    print()
    log.info("[PM] Logging completed")
    return True


def run_sweep_ext(pm, params : Params, scan_label=""):
    """External-laser sweep: arm the PM, wait for the laser's trigger, read.

    Raises SweepCancelled if the user cancels or the wait times out; the PM is
    disarmed first so a late trigger starts nothing.
    """
    global _sweep_count
    _sweep_count += 1
    log.info(f"--- Running instruments (sweep #{_sweep_count}, external laser) ---")

    check_inst(pm)
    arm_pm(pm, params)
    log.info("[PM] Waiting for the external laser sweep")

    _print_instructions(params, scan_label)

    if not wait_for_sweep(pm, params):
        disarm_pm(pm, params)
        check_inst(pm)
        raise SweepCancelled

    return read_pm(pm, params)


if __name__ == "__main__":
    pm, _ = prep_inst(with_laser=False)
