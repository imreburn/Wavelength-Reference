import sys
import dpi_awareness  # noqa: F401  # set Windows DPI awareness before any Tk()
import tkinter as tk
from tkinter import filedialog
import pandas as pd
import json

from constants import APP_VERSION
from plot import display_plot
from structs import Params, Dataset
from save_csv import (COL_CH, COL_REF, COL_SCAN, RAW_DIR)
from logger import setup_logging, fast_exit

def plot_raw(filepath=None, readout=None):
    """Plot a saved raw CSV. `readout` (a readout.PowerReadout) is passed
    through to display_plot; None leaves its Power Readout button disabled."""
    if not filepath:
        root = tk.Tk()
        root.withdraw()
        csv_path = filedialog.askopenfilename(
            initialdir=str(RAW_DIR),
            title="Select CSV file",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        root.destroy()

        if not csv_path:
            log.info(f"No file selected; exiting")
            return False
        else:
            log.info(f"Read successfully: {csv_path}")
    else:
        csv_path = filepath

    with open(csv_path) as f:
        params_dict = json.loads(f.readline().lstrip("# "))
        params = Params(**params_dict)
        df = pd.read_csv(f)

    raw_w = Dataset(unit="W")
    raw_w.data = [df[f'{COL_CH}{i}_{raw_w.unit}'].to_numpy() for i in params.channel]

    raw_w.ref = [df[f'{COL_REF}{i}_{raw_w.unit}'].to_numpy() for i in params.channel] if params.reference else []

    for i in range(1, params.dyn_scans + 1):
        raw_w.scans.append([df[f'{COL_SCAN}{i}_{COL_CH}{ch}_{raw_w.unit}'].to_numpy() for ch in params.channel])

    display_plot(raw_w, params=params, readout=readout)

    return True
    
if __name__ == "__main__":
    log = setup_logging("PlotSweep")
    log.info(f"Version_{APP_VERSION}")
    while plot_raw():
        pass
    fast_exit(0)