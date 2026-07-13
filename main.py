from inst_helper import prep_inst, close_inst
from config_window import get_inputs
from inst_run import run_sweep
from analyze_data import combine_scans
from plot import display_plot
from logger import setup_logging, fast_exit
from structs import Dataset
from constants import APP_VERSION
import shutdown

log = setup_logging("WavelengthSweep")
log.info(f"Version: {APP_VERSION}")

try:
    pm, laser = prep_inst()
    # Exit on laptop-close/system-sleep: the VISA sessions go stale on wake, so
    # a daemon thread hard-exits rather than leaving them held. (Idle-timeout,
    # handled per-window below, is a separate, graceful path.)
    shutdown.start_sleep_watchdog()
    ref_data = []
    auto_run = False  # set by Repeat on the previous plot; auto-Runs this loop

    while True:
        params = get_inputs(pm, laser, auto_run=auto_run)
        if not params:
            break
        
        raw_w = Dataset(unit="W")
        saved_pm_range = params.pm_range
        
        for i in range(1, params.dyn_scans+1):
            log.info(f"Start a scan: {i}")
            raw_w.scans.append(run_sweep(pm, laser, params))            
            params.pm_range -= params.decrement
            
        params.pm_range = saved_pm_range
        raw_w.data = combine_scans(raw_w.scans, params)
        
        if params.reference:
            raw_w.ref = ref_data
        else:
            ref_data = raw_w.data.copy()
        
        auto_run = display_plot(raw_w, params=params)
        # The plot window sets this on idle timeout; its normal close would
        # otherwise loop back to the config window instead of exiting.
        if shutdown.requested():
            break

    close_inst(pm, laser)

except Exception:
    log.exception("Unhandled error")
    raise

# Skip the slow pywebview/.NET native teardown — all work is done and
# instruments are closed, so hard-exit instead of letting the console linger.
fast_exit(0)