from prep_instruments import prep_inst
from gui_input import get_inputs
from run_instruments import run_single
from analyze_data import peak_detection
from backend_plotly import plot_plotly
from save_csv import save_csv_raw, save_csv_peak
from structs import Params

pm, laser = prep_inst()

while True:
    params = get_inputs(pm, laser)
    if not params:
        break
    
    data = run_single(pm, laser, params, dryrun=False)
    
    # Save raw data to CSV
    if  params.csv == 'y':
        save_csv_raw(data, params)
    
    if data is not None:
        peak_info = peak_detection(data)
        # Save max peak information to CSV
        if params.peak_csv == "y" and peak_info is not None:
            save_csv_peak(peak_info, params)
            
        plot_plotly(data, pk=peak_info)