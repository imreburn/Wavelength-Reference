import sys
import dpi_awareness  # noqa: F401  # set Windows DPI awareness before any Tk()
import tkinter as tk
from tkinter import filedialog
import pandas as pd
import numpy as np
import json

from backend_plotly import display_plot
from structs import Params
from save_csv import (COL_X, COL_CH, COL_REF)
from logger import setup_logging, fast_exit

from datapath import data_path

log = setup_logging("PlotSweep")

root = tk.Tk()
root.withdraw()
csv_path = filedialog.askopenfilename(
    initialdir=str(data_path("Raw Data")),
    title="Select CSV file",
    filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
)
root.destroy()

if not csv_path:
    log.error(f"Failed to read: {csv_path}")
    sys.exit(0)
else:
    log.info(f"Read successfully: {csv_path}")

with open(csv_path) as f:
    params_dict = json.loads(f.readline().lstrip("# "))
    params = Params(**params_dict) if params_dict else None
    df = pd.read_csv(f)

data = [df[f'{COL_CH}{i}'].to_numpy() for i in params.channel]

ref = (
    [df[f'{COL_REF}{i}'].to_numpy() for i in params.channel]
    if params.reference
    else None
)

display_plot(data, params=params, ref=ref)

# Skip the slow pywebview/.NET native teardown so the console closes promptly.
fast_exit(0)