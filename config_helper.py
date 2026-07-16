import csv
import tkinter as tk
from datapath import data_path

import logging
log = logging.getLogger(__name__)

FIELD_LABELS = ["Start Wavelength (nm)", "Stop Wavelength (nm)", "Sweep Speed (nm/s)", "Step Size (pm)", "TLS Power (dBm)"]
DEFAULTS = ["0", "0", "0.5", "0.0125", "0.1"]
SWEEP_SPEED_OPTIONS = ["0.5", "1.0", "2.0", "5.0", "10.0", "20.0", "40.0", "50.0", "80.0", "100.0", "150.0", "160.0", "200.0"]

# Extra dropdown-only fields (powermeter range + dynamic-range scanning).
PM_RANGE_LABEL  = "Initial Power Meter Range (dBm)"
DYN_SCAN_LABEL  = "Dynamic Range Scans"
DECREMENT_LABEL = "Decrement (dB)"

PM_RANGE_OPTIONS  = ["10", "0", "-10", "-20", "-30", "-40", "-50", "-60", "-70"]
DYN_SCAN_OPTIONS  = ["1", "2", "3"]
DECREMENT_OPTIONS = ["10", "20", "30", "40"]

EXTRA_LABELS   = [PM_RANGE_LABEL, DYN_SCAN_LABEL, DECREMENT_LABEL]
EXTRA_OPTIONS  = {PM_RANGE_LABEL: PM_RANGE_OPTIONS, DYN_SCAN_LABEL: DYN_SCAN_OPTIONS, DECREMENT_LABEL: DECREMENT_OPTIONS}
EXTRA_DEFAULTS = {PM_RANGE_LABEL: "10", DYN_SCAN_LABEL: "1", DECREMENT_LABEL: "10"}

# Acquisition channel selection (checkboxes 1–4); at least one must be chosen.
CHANNEL_LABEL   = "Input Channel"
CHANNEL_OPTIONS = (1, 2, 3, 4)
CHANNEL_DEFAULT = "1"  # space-separated channel list, as stored in a preset

# Pass/Fail criteria: each label has a min and a max float field, defaulting to 0;
# negative values are rejected. Each label maps to its (min, max) Params attributes.
PASSFAIL_LABELS  = ["Peak Wavelength (nm)", "Peak Depth (dB)", "Peak Width (pm)"]
PASSFAIL_KEYS    = {
    "Peak Wavelength (nm)": ("wl_min", "wl_max"),
    "Peak Depth (dB)"     : ("depth_min", "depth_max"),
    "Peak Width (pm)"     : ("width_min", "width_max"),
}
PASSFAIL_BOUNDS  = ("min", "max")
PASSFAIL_DEFAULT = "0"


def passfail_col(label, bound):
    """CSV column name for a Pass/Fail criterion's min or max field."""
    return f"{label} {bound}"


# Flat list of Pass/Fail preset columns, in (label, bound) order.
PASSFAIL_COLUMNS = [passfail_col(label, b) for label in PASSFAIL_LABELS for b in PASSFAIL_BOUNDS]


def channels_to_str(channels):
    """Serialize a channel tuple/list to the space-separated form stored in presets."""
    return " ".join(str(c) for c in channels)


def parse_channels(s):
    """Parse a space-separated channel string into a tuple of ints (skips junk)."""
    out = []
    for tok in str(s).split():
        try:
            out.append(int(tok))
        except ValueError:
            continue
    return tuple(out)

PRESET_CSV = data_path("preset.csv", mkdir=False)

PADDING = 0.010  # addtional padding in nm

WAV_MIN, WAV_MAX = 1450, 1650


def load_presets():
    """Return {material: {label: value, ...}} from preset.csv, or {} on any failure.

    FIELD_LABELS columns are required; EXTRA_LABELS columns are optional and fall
    back to EXTRA_DEFAULTS only when the column is missing or blank. A non-empty
    value is passed through verbatim (even if it is not a valid dropdown option) so
    the GUI can surface it and reject it on Save, matching the field dropdowns.
    """
    try:
        with open(PRESET_CSV, newline="") as f:
            reader = csv.DictReader(f)
            presets = {}
            for row in reader:
                name = row.get("Name", "").strip()
                if not name:
                    continue
                vals = {label: row[label].strip() for label in FIELD_LABELS}
                for label in EXTRA_LABELS:
                    cell = (row.get(label) or "").strip()
                    vals[label] = cell if cell else EXTRA_DEFAULTS[label]
                cell = (row.get(CHANNEL_LABEL) or "").strip()
                vals[CHANNEL_LABEL] = cell if cell else CHANNEL_DEFAULT
                for col in PASSFAIL_COLUMNS:
                    cell = (row.get(col) or "").strip()
                    vals[col] = cell if cell else PASSFAIL_DEFAULT
                presets[name] = vals
        return presets
    except Exception:
        log.warning("preset.csv not found.")
        return {}


def save_preset(name, vals):
    """Insert or replace `name` in PRESET_CSV with the given label->value dict.

    Existing presets are preserved and a matching name is overwritten in place;
    a new name is appended. Returns None on success or an error message string.
    """
    columns = FIELD_LABELS + EXTRA_LABELS + [CHANNEL_LABEL] + PASSFAIL_COLUMNS
    fieldnames = ["Name"] + columns
    presets = load_presets()
    presets[name] = {col: vals.get(col, "") for col in columns}
    try:
        with open(PRESET_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for nm, row in presets.items():
                writer.writerow({"Name": nm, **row})
        return None
    except Exception as e:
        return f"Could not write {PRESET_CSV}: {e}"


def delete_preset(name):
    """Remove `name` from PRESET_CSV. Returns None on success or an error message string."""
    presets = load_presets()
    if name not in presets:
        return f"Preset '{name}' not found."
    del presets[name]
    fieldnames = ["Name"] + FIELD_LABELS + EXTRA_LABELS + [CHANNEL_LABEL] + PASSFAIL_COLUMNS
    try:
        with open(PRESET_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for nm, row in presets.items():
                writer.writerow({"Name": nm, **row})
        return None
    except Exception as e:
        return f"Could not write {PRESET_CSV}: {e}"


def make_extra_widgets(frame, start_row, init, on_change, enable_dynamic=True):
    """Build the three extra dropdowns starting at grid row `start_row`.

    `init`         dict of label -> initial value (falls back to EXTRA_DEFAULTS).
    `on_change`    callback fired on any selection change.
    `enable_dynamic`  when False, Dynamic Range Scans and Decrement are permanently
                   disabled (reference mode); when True, Decrement is enabled only
                   while Dynamic Range Scans is 2 or 3.

    Returns (vars, menus) — each a dict keyed by label.
    """
    specs = [
        (PM_RANGE_LABEL,  PM_RANGE_OPTIONS),
        (DYN_SCAN_LABEL,  DYN_SCAN_OPTIONS),
        (DECREMENT_LABEL, DECREMENT_OPTIONS),
    ]
    vars_, menus = {}, {}
    for j, (label, options) in enumerate(specs):
        tk.Label(frame, text=label, anchor="e").grid(row=start_row + j, column=0, pady=4, padx=(0, 8), sticky="e")
        v = tk.StringVar(value=init.get(label, EXTRA_DEFAULTS[label]))
        m = tk.OptionMenu(frame, v, *options)
        m.grid(row=start_row + j, column=1, pady=4, sticky="w")
        v.trace_add("write", on_change)
        vars_[label] = v
        menus[label] = m

    def sync_decrement(*_):
        state = "normal" if vars_[DYN_SCAN_LABEL].get() in ("2", "3") else "disabled"
        menus[DECREMENT_LABEL].config(state=state)

    if enable_dynamic:
        vars_[DYN_SCAN_LABEL].trace_add("write", sync_decrement)
        sync_decrement()
    else:
        menus[DYN_SCAN_LABEL].config(state="disabled")
        menus[DECREMENT_LABEL].config(state="disabled")

    return vars_, menus


def validate_inputs(raw_strings, num_data, avg_time):
    """Return (values, None) on success or (None, error_msg) on failure."""
    values = []
    for s in raw_strings:
        try:
            values.append(float(s))
        except ValueError:
            return None, "all fields must be numbers."
    wav_start, wav_stop, sweep_speed, step_size, power_dbm = values[0], values[1], values[2], values[3], values[4]
    
    wav_start    -= PADDING
    wav_stop     += PADDING
    
    if not (WAV_MIN <= wav_start <= WAV_MAX) or not (WAV_MIN <= wav_stop <= WAV_MAX):
        return None, f"Wavelengths must be between {WAV_MIN+PADDING} and {WAV_MAX-PADDING} nm."
    if wav_start >= wav_stop:
        return None, "Start wavelength must be less than Stop wavelength."
    if step_size < 0:
        return None, "Step size must not be less than 0."
    if f"{sweep_speed}" not in SWEEP_SPEED_OPTIONS:
        return None, "Sweep speed must be selected from the dropdown list."
    if power_dbm > 10:
        return None, "TLS power exceeds the maximum (max: 10 dBm)"
    
    avg_t         = int(step_size/sweep_speed*1e3)  # us
    avg_t         = 25 if avg_t < 25 else avg_t
    step_new      = round((sweep_speed/1e3) * avg_t, 4)
    wav_range     = (wav_stop - wav_start) * 1000   # pm
    pp            = int(wav_range // step_new)
    qq            = wav_range % step_new
    num_data_log  = pp if qq == 0 else pp+1
    
    num_data.set(f"{num_data_log:,d}")
    avg_time.set(f"{avg_t:,d}")
    
    if num_data_log > 1000000:
        return None, "Log count exceeds the maximum (max: 1M)"
    
    # values[0]  = wav_start
    # values[1]  = wav_stop
    values[3]  = step_new
    values    += [avg_t, num_data_log]
    
    return values, None


def validate_extras(extra_strs):
    """Return None if every extra dropdown holds a valid option, else an error message.

    `extra_strs`: dict label -> raw string. Decrement is only checked when Dynamic
    Range Scans is 2 or 3 (otherwise the field is unused/disabled). Run before any
    int() conversion so a bad preset value is reported instead of crashing.
    """
    for label in (PM_RANGE_LABEL, DYN_SCAN_LABEL):
        if extra_strs[label] not in EXTRA_OPTIONS[label]:
            return f"{label} must be selected from the dropdown list."
    if extra_strs[DYN_SCAN_LABEL] in ("2", "3") and extra_strs[DECREMENT_LABEL] not in DECREMENT_OPTIONS:
        return f"{DECREMENT_LABEL} must be selected from the dropdown list."
    if int(extra_strs[PM_RANGE_LABEL]) - (int(extra_strs[DYN_SCAN_LABEL]) - 1) * int(extra_strs[DECREMENT_LABEL]) < int(PM_RANGE_OPTIONS[-1]):
        return f"The range cannot be set lower than {PM_RANGE_OPTIONS[-1]} dBm."
    return None


def validate_passfail(raw):
    """Validate the Pass/Fail Criteria fields.

    `raw`: dict label -> (min_str, max_str). Returns (values, None) on success or
    (None, error_msg) on failure, where `values` is dict label -> (min_float, max_float).
    Every field must be a number, none may be negative, and min must not exceed max.
    """
    values = {}
    for label, (lo_s, hi_s) in raw.items():
        lo_s = lo_s.strip() or "0"
        hi_s = hi_s.strip() or "0"
        try:
            lo, hi = float(lo_s), float(hi_s)
        except ValueError:
            return None, "all Pass/Fail Criteria fields must be numbers."
        if lo < 0 or hi < 0:
            return None, "Pass/Fail Criteria values must not be negative."
        if lo > hi:
            if hi == 0:
                hi = float("inf")
            else:
                return None, f"{label}: min must not exceed max."
        if lo == 0 and hi == float("inf"):
            hi = 0
        values[label] = (lo, hi)
    return values, None


def validation_error(msg, result_label, num_data, avg_time, saved, run_btn):
    result_label.config(text=f"Error: {msg}", fg="red")
    saved["ok"] = False
    run_btn.config(state="disabled")
