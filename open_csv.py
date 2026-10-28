import os
import sys
import dpi_awareness  # noqa: F401  # set Windows DPI awareness before any Tk()
import tkinter as tk
from tkinter import filedialog
import pandas as pd
import json
import logging
from dataclasses import fields

from constants import APP_VERSION
from plot import display_plot
from structs import Params, Dataset
from save_csv import (COL_CH, COL_REF, COL_SCAN, RAW_DIR, RAW_FORMAT, range_prefix)
from logger import setup_logging, fast_exit

log = logging.getLogger(__name__)


def plot_raw(filepath=None, readout=None):
    """Plot a saved raw CSV. `readout` (a readout.PowerReadout) is passed
    through to display_plot; None leaves its Power Readout button disabled.

    Returns False when no file was picked, True otherwise (also when the file
    is in an older format: the log says so and the file picker opens again)."""
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

    loaded = read_raw(csv_path)
    if loaded is not None:
        datasets, params = loaded
        display_plot(datasets, params=params, readout=readout)

    return True


def read_raw(csv_path):
    """A raw file's data and settings: (one Dataset per range, Params). None
    for a file in another format than RAW_FORMAT, which the log explains."""
    with open(csv_path) as f:
        params_dict = json.loads(f.readline().lstrip("# "))
        # Files saved before the format number existed are format 1.
        file_format = params_dict.pop("format", 1)
        if file_format != RAW_FORMAT:
            log.error(f"Can't open {os.path.basename(csv_path)}: it was saved by version "
                      f"{params_dict.get('version', 'unknown')} in raw data format {file_format}. "
                      f"This version opens format {RAW_FORMAT} only.")
            return None
        # A key this version doesn't know (one a later version added) is skipped.
        known = {field.name for field in fields(Params)}
        params = Params(**{k: v for k, v in params_dict.items() if k in known})
        df = pd.read_csv(f)

    # One Dataset per range, from its block of columns, cut to its log count:
    # a shorter block's empty cells come back as NaN.
    datasets = []
    for r in range(params.n_ranges):
        p, n = range_prefix(r), params.num_data[r]
        raw_w = Dataset(unit="W")
        column = lambda name: df[f'{p}{name}'].to_numpy()[:n]
        raw_w.data = [column(f'{COL_CH}{i}_{raw_w.unit}') for i in params.channel]

        raw_w.ref = [column(f'{COL_REF}{i}_{raw_w.unit}') for i in params.channel] if params.reference else []

        for i in range(1, params.dyn_scans + 1):
            raw_w.scans.append([column(f'{COL_SCAN}{i}_{COL_CH}{ch}_{raw_w.unit}') for ch in params.channel])
        datasets.append(raw_w)
    return datasets, params

if __name__ == "__main__":
    log = setup_logging("PlotSweep")
    log.info(f"Version_{APP_VERSION}")
    while plot_raw():
        pass
    fast_exit(0)
