import os
import dpi_awareness  # noqa: F401  # set Windows DPI awareness before any Tk()
import tkinter as tk
from tkinter import filedialog
from datetime import datetime
import pandas as pd
import json
from dataclasses import asdict
import logging

from structs import Params, PeakInfo
from datapath import data_path

log = logging.getLogger(__name__)

COL_X   = "Wavelength (nm)"
COL_CH  = "Ch."
COL_REF = "Ref-Ch."
RAW_DIR = "Raw Data"

def save_csv_raw(data, x, params:Params=None, ref=None, file_path=None):
    if file_path is None:
        initial_dir = str(data_path(RAW_DIR))

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
        log.warning("Raw data save cancelled.\n")
        return
    
    df = pd.DataFrame({COL_X:x})
    for ch, power in zip(params.channel, data):
        df[COL_CH+str(ch)] = power
    
    if params.reference and ref:
        for ch, ref_power in zip(params.channel, ref):
            df[COL_REF+str(ch)] = ref_power
    
    with open(file_path, "w", newline="") as f:
        f.write("# " + json.dumps(asdict(params) if params is not None else {}) + "\n")
        df.to_csv(f, index=False)
        
    log.info(f"Saved raw data: {file_path}")


def save_csv_peak_row(label, wl, depth, fwhm, file_path, temperature=None, loss=None, date=None):
    """Append a single peak row (already-resolved values) to the CSV at
    file_path. Used by the interactive 'Save peak info' flow.

    Columns match save_csv_peak() so rows can share one file. A header is
    written only when the target file does not yet exist.
    """
    peak_dict = {
        "Date"           : [date if date is not None else datetime.now().strftime("%Y-%m-%d")],
        "Wavelength (nm)": [round(wl, 6)],
        "Label (SN)"     : [label],
        "I.L."           : [loss],
        "Depth"          : [round(depth, 5)],
        "Width (pm)"     : [round(fwhm, 4)],
        "Temperature"    : [temperature],
    }

    peak_df = pd.DataFrame(data=peak_dict)
    parent = os.path.dirname(file_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    WL_TOL_NM = 0.01  # same-label rows within this wavelength are treated as the same peak

    if os.path.exists(file_path):
        existing_df = pd.read_csv(file_path)
        # Replace an existing row only when it shares this label AND its wavelength
        # is close (within WL_TOL_NM). Same-label rows at a clearly different
        # wavelength are kept, so distinct peaks can coexist under one label.
        same_label = existing_df["Label (SN)"].astype(str) == str(label)
        close_wl = (existing_df["Wavelength (nm)"] - round(wl, 6)).abs() <= WL_TOL_NM
        if (close_wl & same_label).any():
            log.info(f"One or more existing peak data will be overwritten by this peak: {peak_df["Wavelength (nm)"]}")
        existing_df = existing_df[~(same_label & close_wl)]
        peak_df = pd.concat([existing_df, peak_df], ignore_index=True)
        peak_df.to_csv(file_path, index=False)
    else:
        peak_df.to_csv(file_path, index=False)
    
    log.info(f"Saved peak data: {file_path}")