from prep_instruments import prep_inst
from gui_input_reference import get_inputs
from run_instruments import run_sweep
from backend_plotly import display_plot
from structs import Params
from logger import setup_logging

log = setup_logging("RefSweep")

try:
    pm, laser = prep_inst()

    ref_data = None  

    while True:
        params = get_inputs(ref_saved=ref_data is not None)
        if not params:
            break

        data = run_sweep(pm, laser, params, dryrun=False)
    
        if params.sweep_type == "new_reference":
            ref_data = data
            display_plot(ref_data)
        
        else:  # "reference" — measure against the stored reference  
            comp_data = (data[0], data[1] - ref_data[1])
            display_plot(comp_data, params=params, overlays=[ref_data])

except Exception:
    log.exception("Unhandled error")
    raise