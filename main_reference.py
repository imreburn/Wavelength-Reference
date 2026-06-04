from prep_instruments import prep_inst
from gui_input_reference import get_inputs
from run_instruments import run_single
from analyze_data import peak_detection
from backend_plotly import display_plot
from structs import Params
from logger import setup_logging

log = setup_logging("RefSweep")

try:
    pm, laser = prep_inst()

    ref_data = None  # most recent reference sweep; cell sweeps are compared against it

    while True:
        params = get_inputs()
        if not params:
            break

        data = run_single(pm, laser, params, dryrun=False)
        
        if data is None:
            log.warning("Data is not collected.")
            continue

        if params.sweep == "reference":
            ref_data = data
            log.info("Reference sweep stored.")
        else:  # "cell" — measure against the stored reference
            if ref_data is None:
                log.warning("Cell sweep with no reference set; skipping comparison.")
                continue
            
            data[:, 1] = data[:, 1] - ref_data[:, 1]
            peak_info = peak_detection(data)
            display_plot(data, pk=peak_info)

except Exception:
    log.exception("Unhandled error")
    raise