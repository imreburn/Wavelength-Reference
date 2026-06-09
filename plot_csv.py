import os
import sys
import tkinter as tk
from tkinter import filedialog
import pandas as pd
import numpy as np
import json

from backend_plotly import display_plot
from structs import Params

root = tk.Tk()
root.withdraw()
script_dir = os.path.dirname(os.path.abspath(__file__))
csv_path = filedialog.askopenfilename(
    initialdir=script_dir,
    title="Select CSV file",
    filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
)
root.destroy()

if not csv_path:
    sys.exit(0)

params = None

if "keysight" in csv_path:
    df = pd.read_csv(csv_path, skiprows=19, header=None, names=["Wavelength", "Power"])
    df.set_index("Wavelength")
    df["Wavelength"] = df["Wavelength"] * 1e9
else:
    with open(csv_path) as f:
        params_dict = json.loads(f.readline().lstrip("# "))
        params = Params(**params_dict) if params_dict else None
        df = pd.read_csv(f)
        
data_np  = df.to_numpy()
display_plot((data_np[:, 0], data_np[:, 1]), params=params)