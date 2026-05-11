import os
import sys
import tkinter as tk
from tkinter import filedialog
import pandas as pd

from analyze_data import plot_matplotlib, plot_plotly, peak_analysis


def ask_backend():
    chosen = {}

    def on_ok():
        chosen["backend"] = var.get()
        root.destroy()

    root = tk.Tk()
    var = tk.StringVar(value="matplotlib")
    root.title("Plot Options")
    root.resizable(False, False)
    frame = tk.Frame(root, padx=20, pady=15)
    frame.pack()
    tk.Label(frame, text="Plotting backend", anchor="w", width=20).grid(row=0, column=0, pady=4, sticky="w")
    tk.OptionMenu(frame, var, "matplotlib", "plotly").grid(row=0, column=1, pady=4, sticky="w")
    tk.Button(frame, text="OK", command=on_ok, width=10).grid(row=1, column=0, columnspan=2, pady=8)
    root.mainloop()
    return chosen.get("backend", "matplotlib")


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


peak_info = peak_analysis(df)

backend = ask_backend()
if backend == "plotly":
    plot_plotly(df)
else:
    plot_matplotlib(df, peak_info)
