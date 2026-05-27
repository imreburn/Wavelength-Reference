import os
import sys
import tkinter as tk
from tkinter import filedialog
import pandas as pd
import numpy as np

from backend_plotly import plot_plotly
from analyze_data import peak_detection

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

if "keysight" in csv_path:
    df = pd.read_csv(csv_path, skiprows=19, header=None, names=["Wavelength", "Power"])
    df.set_index("Wavelength")
else:
    df = pd.read_csv(csv_path)

data = df.to_numpy()
peak_info = peak_detection(data)
plot_plotly(data, pk=peak_info)