import os
import sys
import tkinter as tk
from tkinter import filedialog
import pandas as pd

import plot

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

# Pick one
# plot.matplotlib_plain(df)
plot.simple_analysis(df)
# plot.plotly_plain(df)
