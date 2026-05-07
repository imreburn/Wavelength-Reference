from gui_input import get_inputs
from run_instruments import run
from prep_instruments import prep_inst

pm, laser = prep_inst()

while True:
    params = get_inputs(pm, laser)
    if not params:
        break
    run(params, pm, laser)
