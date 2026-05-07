import os
import sys
import tkinter as tk
from tkinter import filedialog
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px

from plot import plot_data, simple_analysis

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

# Plain plot with matplotlib
# plt.plot(df["Wavelength"], df["Power"])
# plt.show()

# Analyze data, still plotting with matplotlib
simple_analysis(df)
# plot_data(df)

# Plot with plotly
# fig = px.line(df, x="Wavelength", y="Power")
# fig.show()