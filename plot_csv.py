import os
import sys
import tkinter as tk
from tkinter import filedialog
import pandas as pd

from backend_matplotlib import plot_matplotlib
from backend_plotly import plot_plotly
from analyze_data import peak_detection

def ask_backend():
    chosen = {}

    def on_ok():
        chosen["backend"] = var.get()
        root.destroy()

    root = tk.Tk()
    var = tk.StringVar(value="plotly")
    root.title("Plot Options")
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.resizable(False, False)
    frame = tk.Frame(root, padx=20, pady=15)
    frame.pack()
    tk.Label(frame, text="Plotting backend", anchor="w", width=20).grid(row=0, column=0, pady=4, sticky="w")
    tk.OptionMenu(frame, var, "plotly", "matplotlib").grid(row=0, column=1, pady=4, sticky="w")
    tk.Button(frame, text="OK", command=on_ok, width=10).grid(row=1, column=0, columnspan=2, pady=8)
    root.mainloop()
    return chosen.get("backend", None)


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

backend = ask_backend()

peak_info = peak_detection(df)

if not backend:
    sys.exit(0)
elif backend == "plotly":
    plot_plotly(df, peak_info=peak_info)
elif backend == "matplotlib":
    plot_matplotlib(df, peak_info=peak_info)
