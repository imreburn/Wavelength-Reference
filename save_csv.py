import os
import tkinter as tk
from tkinter import filedialog
from datetime import datetime
import pandas as pd

from structs import Params, PeakInfo

def save_csv_raw(data, file_path=None):

    df = pd.DataFrame(data, columns=["Wavelength", "Power"])

    if file_path is None:
        initial_dir = os.path.join("Test Results", "Raw Data")
        os.makedirs(initial_dir, exist_ok=True)

        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.asksaveasfilename(
            initialdir=initial_dir,
            title="Save raw data as",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        root.destroy()

    if not file_path:
        print("Raw data save cancelled.\n")
        return

    df.to_csv(file_path, index=False)
    print("Raw data saved to a file: ", file_path, "\n")


# def save_csv_raw(data, params: Params):
    
#     df = pd.DataFrame(data, columns=["Wavelength", "Power"])
#     os.makedirs(os.path.join("Test Results", "Raw Data", params.date), exist_ok=True)
#     file_path = os.path.join("Test Results", "Raw Data", params.date, params.csv_fname)
#     df.to_csv(file_path, index=False)    
#     print("Raw data saved to a file: ", file_path, "\n")

    
def save_csv_peak(peak_info: PeakInfo, params: Params):
    # Construct pandas DataFrame
    peak_dict = {
        "Label"      : [params.peak_label],
        "Timestamp"  : [params.time],
        "Wavelength" : [peak_info.csv.wl],
        "Depth (max)": [peak_info.csv.depth],
        "FWHM (max)" : [peak_info.csv.fwhm]
    }
    
    peak_df = pd.DataFrame(data=peak_dict)
    os.makedirs(os.path.join("Test Results", "Peaks"), exist_ok=True)
    csv_path = os.path.join("Test Results", "Peaks", params.peak_fname)
    peak_df.to_csv(csv_path, index=False, mode='a', header=not os.path.exists(csv_path))
    print("Peak information saved to a file: ", csv_path, "\n")


def save_csv_peak_row(label, wl, depth, fwhm, file_path, temperature=None, loss=None):
    """Append a single peak row (already-resolved values) to the CSV at
    file_path. Used by the interactive 'Save peak info' flow.

    Columns match save_csv_peak() so rows can share one file. A header is
    written only when the target file does not yet exist.
    """
    peak_dict = {
        "Date"           : [datetime.now().strftime("%Y-%m-%d")],
        "Wavelength (nm)": [round(wl, 6)],
        "Label"          : [label],
        "I.L."           : [loss],
        "Depth"          : [round(depth, 5)],
        "Width (pm)"     : [round(fwhm, 4)],
        "Temperature"    : [temperature],
    }

    peak_df = pd.DataFrame(data=peak_dict)
    parent = os.path.dirname(file_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    WL_TOL_NM = 0.5  # same-label rows within this wavelength are treated as the same peak

    if os.path.exists(file_path):
        existing_df = pd.read_csv(file_path)
        # Replace an existing row only when it shares this label AND its wavelength
        # is close (within WL_TOL_NM). Same-label rows at a clearly different
        # wavelength are kept, so distinct peaks can coexist under one label.
        same_label = existing_df["Label"].astype(str) == str(label)
        close_wl = (existing_df["Wavelength (nm)"] - round(wl, 6)).abs() <= WL_TOL_NM
        existing_df = existing_df[~(same_label & close_wl)]
        peak_df = pd.concat([existing_df, peak_df], ignore_index=True)
        peak_df.to_csv(file_path, index=False)
    else:
        peak_df.to_csv(file_path, index=False)
    print("Peak information saved to a file: ", file_path, "\n")
    return file_path