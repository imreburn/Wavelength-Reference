from prep_instruments import prep_inst
from gui_input_single import get_inputs
from run_instruments import run_single
from analyze_data import peak_detection
from backend_plotly import display_plot
from structs import Params

pm, laser = prep_inst()

while True:
    params = get_inputs(pm, laser)
    if not params:
        break
    
    data = run_single(pm, laser, params, dryrun=False)
    
    if data is not None:
        peak_info = peak_detection(data)
        display_plot(data, pk=peak_info)
    else:
        print("Data is not collected.")