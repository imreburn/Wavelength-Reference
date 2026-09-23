from inst_helper import prep_inst, close_inst, InstrumentError
from config_window import get_inputs
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

log = setup_logging("WavelengthSweep")
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
    print()


pm = laser = None   # bound before the try, so the finally below can close them

try:
    # The source is fixed for the whole session: it decides what to connect
    # and which sweep function the loop calls.
    source   = select_source()
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
        if not params:
            break

        raw_w = Dataset(unit="W")
        saved_pm_range = params.pm_range

        try:
            for i in range(1, params.dyn_scans+1):
                log.info(f"Start a scan: {i}")
                if external:
                    label = f"Scan {i} of {params.dyn_scans}" if params.dyn_scans > 1 else ""
                    scan = run_sweep_ext(pm, params, label)
                else:
                    scan = run_sweep(pm, laser, params)
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
        raw_w.data = combine_scans(raw_w.scans)
        
        if params.reference:
            raw_w.ref = ref_data
        else:
            ref_data = raw_w.data.copy()

        # Auto-save after the reference is attached, so the file matches what
        # "Save raw data..." would write. A failure is shown on the plot rather
        # than ending the session; the button is still there as a fallback.
        autosaved_to, autosave_error = None, None
        if params.save_raw:
            try:
                autosaved_to = auto_raw_path(params)
                save_csv_raw(raw_w, params=params, file_path=autosaved_to)
            except Exception as e:
                log.exception("Auto-save of raw data failed")
                autosaved_to, autosave_error = None, str(e)

        auto_run = display_plot(raw_w, params=params, readout=readout,
                                autosaved_to=autosaved_to, autosave_error=autosave_error)
        # The plot window sets this on idle timeout; its normal close would
        # otherwise loop back to the config window instead of exiting.
        if shutdown.requested():
            break

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