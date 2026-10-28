import dpi_awareness  # noqa: F401  # set Windows DPI awareness before any Tk()
import tkinter as tk
from tkinter import filedialog
import pandas as pd
import json
from dataclasses import asdict
import logging

from structs import Params, Dataset
from plot_helper import gen_xaxis
from datapath import data_path

log = logging.getLogger(__name__)

COL_X    = "Wavelength_nm"
COL_CH   = "Ch"
COL_REF  = "Ref_" + COL_CH
COL_SCAN = "Scan"
RAW_DIR   = data_path("Raw Data")
PEAKS_DIR = data_path("Peaks")

# The raw file's layout, written into its first line as "format". 2: one
# column block per wavelength range, each column's name starting with the
# range (R1_Wavelength_nm, R1_Ch1_W, ...), even for a single range. Files
# without the key are format 1, one range with unprefixed names. open_csv
# reads format 2 only.
RAW_FORMAT = 2


def range_prefix(r):
    """The start of range r's column names in a raw file: R1_, R2_, ..."""
    return f"R{r + 1}_"


def auto_raw_path(params: Params):
    """Auto-save path: Raw Data/<label>_<time>.csv, or <time>.csv with no label.

    params.time is YYYY-MM-DD_HH-MM-SS, stamped when Run is pressed. A name
    already taken (two runs in the same second) gets _2, _3, ... appended.
    """
    stem = f"{params.label}_{params.time}" if params.label else params.time
    path = RAW_DIR / f"{stem}.csv"
    n = 2
    while path.exists():
        path = RAW_DIR / f"{stem}_{n}.csv"
        n += 1
    return str(path)


def save_csv_raw(datasets: list[Dataset], params: Params, file_path=None):
    """Save the sweep, one Dataset per range, as a raw file (RAW_FORMAT).

    Each range is a block of columns side by side, as many rows long as its
    log count; a shorter block's cells below its end are empty.
    """
    if file_path is None:
        initial_dir = str(RAW_DIR)

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
    
    blocks = []
    for r, raw_w in enumerate(datasets):
        p = range_prefix(r)
        wav_range, _, _ = gen_xaxis(params, r)
        df = pd.DataFrame({f'{p}{COL_X}': wav_range})
        
        for ch, power in zip(params.channel, raw_w.data):
            df[f'{p}{COL_CH}{ch}_{raw_w.unit}'] = power
        
        if params.reference:
            for ch, ref_power in zip(params.channel, raw_w.ref):
                df[f'{p}{COL_REF}{ch}_{raw_w.unit}'] = ref_power
                
        for s_idx, scan in enumerate(raw_w.scans, start=1):
            for ch, spectrum in zip(params.channel, scan):
                df[f'{p}{COL_SCAN}{s_idx}_{COL_CH}{ch}_{raw_w.unit}'] = spectrum
        blocks.append(df)
    # Side by side on the row index: a shorter block gets NaN, an empty cell.
    df = pd.concat(blocks, axis=1)
    
    with open(file_path, "w", newline="") as f:
        f.write("# " + json.dumps({"format": RAW_FORMAT, **asdict(params)}) + "\n")
        df.to_csv(f, index=False)
        
    log.info(f"Saved raw data: {file_path}")
