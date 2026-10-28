from inst_helper import prep_inst, close_inst, InstrumentError
from config_window import get_inputs, mark_ref_available, advance_label, relabel
from inst_run import run_sweep, SweepCancelled
from inst_run_ext import run_sweep_ext
from analyze_data import combine_scans
from plot import display_plot
from save_csv import save_csv_raw, auto_raw_path
from readout import PowerReadout
from logger import setup_logging, fast_exit
from structs import Dataset
from constants import APP_VERSION, TLS_SOURCES
import shutdown
import gc

log = setup_logging("MultiSweep")
log.info(f"Version_{APP_VERSION}")


def select_source():
    """Console menu for the laser source. Returns a TLS_SOURCES key.
    Enter alone picks the first entry. Ctrl+C (or a closed stdin) exits
    cleanly — nothing is connected yet, so there is nothing to release.
    """
    names = list(TLS_SOURCES)
    bar = "=" * 60
    print()
    print(" Select the laser source")
    print(bar)
    for i, name in enumerate(names, start=1):
        info = TLS_SOURCES[name]
        how = "must be set manually" if info["external"] else "controlled by this app"
        print(f"   {i}. {name}  ({info['wl_min']}-{info['wl_max']} nm), {how}")
    print(bar)
    try:
        while True:
            raw = input(f" Enter a number 1-{len(names)} [1]: ").strip()
            if raw == "":
                return names[0]
            if raw.isdigit() and 1 <= int(raw) <= len(names):
                return names[int(raw) - 1]
            print(f" Please enter a number from 1 to {len(names)}.")
    except (KeyboardInterrupt, EOFError):
        print()
        log.info("No laser source selected — exiting.")
        fast_exit(0)

pm = laser = None   # bound before the try, so the finally below can close them

try:
    # The source is fixed for the whole session: it decides what to connect
    # and which sweep function the loop calls.
    source   = select_source()
    print()
    external = TLS_SOURCES[source]["external"]
    log.info(f"Laser source: {source}" + (" (external)" if external else ""))
    pm, laser = prep_inst(with_laser=not external)

    # The live power readout, shared by the config window (as a section) and
    # the plot window (as a modal). One per session, so its max carries over.
    readout = PowerReadout(pm, laser, TLS_SOURCES[source])

    # Exit on laptop-close/system-sleep: the VISA sessions go stale on wake, so
    # a daemon thread hard-exits rather than leaving them held. (Idle-timeout,
    # handled per-window below, is a separate, graceful path.)
    shutdown.start_sleep_watchdog()
    ref_data = []
    auto_run = False  # set by Repeat on the previous plot; auto-Runs this loop

    while True:
        params = get_inputs(readout, auto_run=auto_run, source=source)
        # The closed config window leaves Tk variables in reference cycles (the
        # readout section's 19, via the self-rescheduling idle poll). Free them
        # here, on the thread that owns Tcl. Left to the GC, they can be freed on
        # a Dash worker thread while the plot loads, where each one blocks ~1 s
        # and raises "main thread is not in main loop".
        gc.collect()
        if not params:
            break

        # One Dataset per wavelength range. The ranges run in order, each with
        # all its dynamic-range scans, from the initial meter range, before
        # the next.
        datasets = [Dataset(unit="W") for _ in range(params.n_ranges)]
        saved_pm_range = params.pm_range

        try:
            for r, raw_w in enumerate(datasets):
                params.pm_range = saved_pm_range
                for i in range(1, params.dyn_scans+1):
                    log.info(f"Start a scan: range {r + 1}, scan {i}")
                    if external:
                        parts = ([f"Range {r + 1} of {params.n_ranges}"] if params.n_ranges > 1 else []) \
                                + ([f"Scan {i} of {params.dyn_scans}"] if params.dyn_scans > 1 else [])
                        scan = run_sweep_ext(pm, params, r, ", ".join(parts))
                    else:
                        scan = run_sweep(pm, laser, params, r)
                    raw_w.scans.append(scan)
                    params.pm_range -= params.decrement
        except SweepCancelled:
            # Nothing from this Run is kept, earlier scans included: a partial
            # dynamic-range set would plot like a complete one. auto_run must be
            # cleared or a Repeat would re-arm the meter the moment the config
            # window reopens.
            auto_run = False
            log.info("Sweep cancelled — back to the configuration window.")
            if shutdown.requested():          # idle timeout while armed
                break
            continue
        except InstrumentError as e:
            # SweepFailed and every other instrument complaint (stuck *OPC?, a
            # laser that re-locked, a jammed error queue). The session is still
            # usable, so drop the run and let the user try again.
            auto_run = False
            log.error("Sweep failed: %s — back to the configuration window.", e)
            continue

        params.pm_range = saved_pm_range
        for raw_w in datasets:
            raw_w.data = combine_scans(raw_w.scans)
        # The sweep finished, so its label is used: move the counter on.
        advance_label()

        # The reference is kept per range. "Use reference" needs the same
        # parameters (Change deletes it), so it has the same ranges.
        if params.reference:
            for raw_w, ref in zip(datasets, ref_data):
                raw_w.ref = ref
        else:
            ref_data = [raw_w.data.copy() for raw_w in datasets]
            mark_ref_available()

        # Auto-save after the reference is attached, so the file matches what
        # "Save raw data..." would write. A failure is shown on the plot rather
        # than ending the session; the button is still there as a fallback.
        autosaved_to, autosave_error = None, None
        if params.save_raw:
            try:
                autosaved_to = auto_raw_path(params)
                save_csv_raw(datasets, params=params, file_path=autosaved_to)
            except Exception as e:
                log.exception("Auto-save of raw data failed")
                autosaved_to, autosave_error = None, str(e)

        # The graph window can change params.label (its Label field).
        run_label = params.label
        auto_run = display_plot(datasets, params=params, readout=readout,
                                autosaved_to=autosaved_to, autosave_error=autosave_error)
        # The plot window sets this on idle timeout; its normal close would
        # otherwise loop back to the config window instead of exiting.
        if shutdown.requested():
            break
        # A changed label moves the counter on, or, when it doesn't fit the
        # prefix and counter, the config window waits for Run and says why.
        if relabel(run_label, params.label):
            auto_run = False

except Exception:
    log.exception("Unhandled error")
    raise

finally:
    # Runs on the normal exit and on any escaping error, so the shutter never
    # stays open: with the per-sweep power-off disabled, this is the only
    # place the laser is turned off.
    close_inst(pm, laser)

# Skip the slow pywebview/.NET native teardown — all work is done and
# instruments are closed, so hard-exit instead of letting the console linger.
fast_exit(0)