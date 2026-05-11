from prep_instruments import prep_inst
from gui_input import get_inputs
from run_instruments import run
from analyze_data import analyze

pm, laser = prep_inst()

while True:
    params = get_inputs(pm, laser)
    # print(params)
    if not params:
        break
    
    df = run(params, pm, laser, dryrun=False)
    
    analyze(df, params)