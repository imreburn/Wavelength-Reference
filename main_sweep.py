import numpy as np

from prep_instruments import prep_inst
from gui_input_sweep import get_inputs
from run_instruments import run_sweep
from analyze_data import combine_scans
from backend_plotly import display_plot
from structs import Params
from logger import setup_logging

log = setup_logging("WavelengthSweep")

try:
    pm, laser = prep_inst()
    last_data = None

    while True:
        params = get_inputs()
        if not params:
            break
        
        scans = []
        saved_pm_range = params.pm_range
        
        for i in range(1, params.dyn_scans+1):
            log.info(f"Start a scan: {i}")
            scan = run_sweep(pm, laser, params, dryrun=False)
            scans.append((params.pm_range, scan))            
            params.pm_range -= params.decrement
            
        data = combine_scans(scans)
        params.pm_range = saved_pm_range
        
        if not params.reference:
            last_data = data.copy()
        
        display_plot(data, params=params, ref=last_data, overlays=[e[1] for e in scans])
            
except Exception:
    log.exception("Unhandled error")
    raise