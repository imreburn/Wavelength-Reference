from prep_instruments import prep_inst
from gui_input_sweep import get_inputs
from run_instruments import run_sweep
from analyze_data import combine_scans
from backend_plotly import display_plot
from structs import Params
from logger import setup_logging

# from backend_plotly_tmp import display_plot_tmp
from backend_matplotlib import plot_matplotlib
from save_csv import save_csv_raw

log = setup_logging("WavelengthSweep")

try:
    pm, laser = prep_inst()

    while True:
        params = get_inputs()
        if not params:
            break
        
        if params.sweep_type == "single":
            data      = run_sweep(pm, laser, params, dryrun=False)
            display_plot(data, params=params)
            
        elif params.sweep_type == "dynamic":
            scans = []
            for i in range(params.dyn_scans):
                log.info(f"Start a scan: {i+1}")
                scan = run_sweep(pm, laser, params, dryrun=False)
                scans.append((params.pm_range, scan))            
                params.pm_range -= params.decrement

            data = combine_scans(scans)
            display_plot(data, params=params, overlays=[e[1] for e in scans])
            
except Exception:
    log.exception("Unhandled error")
    raise