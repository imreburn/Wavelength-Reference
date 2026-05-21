from prep_instruments import prep_inst
from gui_input import get_inputs
from run_instruments import run
from analyze_data import peak_detection
from backend_matplotlib import plot_matplotlib
from backend_plotly import plot_plotly

pm, laser = prep_inst()

while True:
    params = get_inputs(pm, laser)
    if not params:
        break
    
    df = run(params, pm, laser, dryrun=False)
    
    peak_info = peak_detection(df, params)

    if params["plot_backend"] == "plotly":
        plot_plotly(df, peak_info=peak_info)
    elif params["plot_backend"] == "matplotlib":
        plot_matplotlib(df, peak_info=peak_info)