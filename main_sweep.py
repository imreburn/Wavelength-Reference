from prep_instruments import prep_inst, close_inst
from gui_input_sweep import get_inputs
from run_instruments import run_sweep
from analyze_data import combine_scans
from backend_plotly import display_plot
from logger import setup_logging, fast_exit

log = setup_logging("WavelengthSweep")

try:
    pm, laser = prep_inst()
    last_data = None
    auto_run = False  # set by Repeat on the previous plot; auto-Runs this loop

    while True:
        params = get_inputs(pm, laser, auto_run=auto_run)
        if not params:
            break
        
        scans = []
        saved_pm_range = params.pm_range
        
        for i in range(1, params.dyn_scans+1):
            log.info(f"Start a scan: {i}")
            scans.append(run_sweep(pm, laser, params, dryrun=False))            
            params.pm_range -= params.decrement
            
        params.pm_range = saved_pm_range
        data = combine_scans(scans, params)
        
        if not params.reference:
            last_data = data.copy()
        
        auto_run = display_plot(data, params=params, ref=last_data, overlays=scans)
    
    close_inst(pm, laser)

except Exception:
    log.exception("Unhandled error")
    raise

# Skip the slow pywebview/.NET native teardown — all work is done and
# instruments are closed, so hard-exit instead of letting the console linger.
fast_exit(0)