from gui_input import get_inputs
from run_instruments import run


while True:
    params = get_inputs()
    if not params:
        break
    run(params)
