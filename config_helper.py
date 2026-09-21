import csv
import math
import tkinter as tk
from tkinter import ttk
from datapath import data_path

import logging
log = logging.getLogger(__name__)

FIELD_LABELS = ["Start Wavelength (nm)", "Stop Wavelength (nm)", "Sweep Speed (nm/s)", "Step Size (pm)", "TLS Power (dBm)"]
DEFAULTS = ["0", "0", "0.5", "0.0125", "0.1"]
SWEEP_SPEED_OPTIONS = ["0.5", "1.0", "2.0", "5.0", "10.0", "20.0", "40.0", "50.0", "80.0", "100.0", "150.0", "160.0", "200.0"]

# Extra dropdown-only fields (sweep padding, powermeter range + dynamic-range scanning).
PADDING_LABEL   = "Wavelength Padding (pm)"
PM_RANGE_LABEL  = "Initial Power Meter Range (dBm)"
DYN_SCAN_LABEL  = "Dynamic Range Scans"
DECREMENT_LABEL = "Decrement (dB)"

PADDING_OPTIONS   = ["0", "10", "20", "30", "40", "50"]
PM_RANGE_OPTIONS  = ["10", "0", "-10", "-20", "-30", "-40", "-50", "-60", "-70"]
DYN_SCAN_OPTIONS  = ["1", "2", "3"]
DECREMENT_OPTIONS = ["10", "20", "30", "40"]

EXTRA_LABELS   = [PADDING_LABEL, PM_RANGE_LABEL, DYN_SCAN_LABEL, DECREMENT_LABEL]
EXTRA_OPTIONS  = {PADDING_LABEL: PADDING_OPTIONS, PM_RANGE_LABEL: PM_RANGE_OPTIONS, DYN_SCAN_LABEL: DYN_SCAN_OPTIONS, DECREMENT_LABEL: DECREMENT_OPTIONS}
EXTRA_DEFAULTS = {PADDING_LABEL: "50", PM_RANGE_LABEL: "10", DYN_SCAN_LABEL: "1", DECREMENT_LABEL: "10"}


def padding_nm(s):
    """Convert a padding dropdown value (picometer string) to nm."""
    return int(s) / 1000.0

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


# More Info: an optional per-run label (prefix + zero-padded counter) and the
# auto-save switch. Session-only UI state — never written to presets.
LABEL_DIGIT_OPTIONS = ["0", "1", "2", "3", "4"]
LABEL_DIGIT_DEFAULT = "0"
LABEL_START_DEFAULT = "1"
# The label goes into the auto-save filename, so reject what Windows forbids.
FILENAME_BAD_CHARS  = '\\/:*?"<>|'


def build_label(prefix, digits, n):
    """prefix followed by n zero-padded to `digits` places; just prefix for 0 digits."""
    return prefix + (f"{n:0{digits}d}" if digits else "")


def validate_label(prefix, digits_s, start_s):
    """Validate the More Info label fields.

    Returns (label, n, None) on success or (None, None, error_msg) on failure,
    where n is the counter value (None when digits is 0). The prefix is kept as
    text, so leading zeros survive.
    """
    if digits_s not in LABEL_DIGIT_OPTIONS:
        return None, None, "label digits must be selected from the dropdown list."
    digits = int(digits_s)
    if any(c in FILENAME_BAD_CHARS for c in prefix):
        return None, None, f"label prefix must not contain any of {FILENAME_BAD_CHARS}"
    if prefix != prefix.rstrip(" ."):
        return None, None, "label prefix must not end with a space or a dot."
    n = None
    if digits:
        start_s = start_s.strip()
        if not (start_s.isascii() and start_s.isdigit()):   # isdigit alone accepts "²"
            return None, None, "label 'starting from' must be a whole number."
        n = int(start_s)
        limit = 10 ** digits - 1
        if n > limit:
            return None, None, f"label counter is over {limit}, the {digits}-digit limit."
    label = build_label(prefix, digits, n)
    if not label:
        return None, None, "label is empty. Enter a prefix or choose 1 or more digits."
    return label, n, None


# SI prefixes from 10^-24 to 10^24; index 8 is the blank (10^0) slot, which keeps
# an unprefixed unit in the same column as a prefixed one in right-aligned labels.
SI_PREFIXES = "yzafpnµm kMGTPEZY"


def eng_format(x, unit="", digits=3):
    """Format x in engineering notation with an SI prefix, e.g. 1.234 µW.

    Never raises: magnitudes outside 10^±24 clamp to y/Y, and nan/inf pass
    through. Live readouts call this from a Tk `after` loop, where an exception
    would kill the loop rather than just garble one label.
    """
    if not math.isfinite(x):
        return f"{x} {unit}"
    exp = 0 if x == 0 else math.floor(math.log10(abs(x)) / 3) * 3
    exp = max(-24, min(24, exp))
    mant = round(x / 10.0**exp, digits) + 0.0  # + 0.0 folds -0.0 into 0.0
    if abs(mant) >= 1000 and exp < 24:         # rounding pushed us up a decade
        exp += 3
        mant = round(x / 10.0**exp, digits)
    return f"{mant:.{digits}f} {SI_PREFIXES[exp // 3 + 8]}{unit}"


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


def preset_path(source):
    return data_path(f"preset_{source}.csv", mkdir=False)


def load_presets(path):
    """Return {material: {label: value, ...}} from preset.csv, or {} on any failure.

    FIELD_LABELS columns are required; EXTRA_LABELS columns are optional and fall
    back to EXTRA_DEFAULTS only when the column is missing or blank. A non-empty
    value is passed through verbatim (even if it is not a valid dropdown option) so
    the GUI can surface it and reject it on Save, matching the field dropdowns.
    """
    try:
        with open(path, newline="") as f:
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
        log.warning("%s not found.", path)
        return {}


def save_preset(path, name, vals):
    """Insert or replace `name` in path with the given label->value dict.

    Existing presets are preserved and a matching name is overwritten in place;
    a new name is appended. Returns None on success or an error message string.
    """
    columns = FIELD_LABELS + EXTRA_LABELS + [CHANNEL_LABEL] + PASSFAIL_COLUMNS
    fieldnames = ["Name"] + columns
    presets = load_presets(path)
    presets[name] = {col: vals.get(col, "") for col in columns}
    try:
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for nm, row in presets.items():
                writer.writerow({"Name": nm, **row})
        return None
    except Exception as e:
        return f"Could not write {path}: {e}"


def delete_preset(path, name):
    """Remove `name` from path. Returns None on success or an error message string."""
    presets = load_presets(path)
    if name not in presets:
        return f"Preset '{name}' not found."
    del presets[name]
    fieldnames = ["Name"] + FIELD_LABELS + EXTRA_LABELS + [CHANNEL_LABEL] + PASSFAIL_COLUMNS
    try:
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for nm, row in presets.items():
                writer.writerow({"Name": nm, **row})
        return None
    except Exception as e:
        return f"Could not write {path}: {e}"


def section_header(frame, text, row):
    """Place a bold section title plus a horizontal separator line below it."""
    tk.Label(frame, text=text, font=("TkDefaultFont", 10, "bold"), anchor="w").grid(
        row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))
    ttk.Separator(frame, orient="horizontal").grid(
        row=row + 1, column=0, columnspan=2, sticky="ew", pady=(0, 6))


def make_extra_widgets(frame, start_row, init, on_change, enable_dynamic=True):
    """Build the extra dropdowns, one per EXTRA_LABELS row, from grid row `start_row`.

    `init`         dict of label -> initial value (falls back to EXTRA_DEFAULTS).
    `on_change`    callback fired on any selection change.
    `enable_dynamic`  when False, Dynamic Range Scans and Decrement are permanently
                   disabled (reference mode); when True, Decrement is enabled only
                   while Dynamic Range Scans is 2 or 3.

    Returns (vars, menus) — each a dict keyed by label.
    """
    vars_, menus = {}, {}
    for j, label in enumerate(EXTRA_LABELS):
        tk.Label(frame, text=label, anchor="e").grid(row=start_row + j, column=0, pady=4, padx=(0, 8), sticky="e")
        v = tk.StringVar(value=init.get(label, EXTRA_DEFAULTS[label]))
        m = tk.OptionMenu(frame, v, *EXTRA_OPTIONS[label])
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


def validate_inputs(raw_strings, num_data, avg_time, padding, source_spec):
    """Return (values, None) on success or (None, error_msg) on failure.

    `padding` is the extra sweep range added on each side, in nm (0 for none).
    It widens the range the log count and bounds check are computed over, but the
    returned start/stop stay as entered — inst_run/plot_helper re-apply it from
    Params.padding.

    `source_spec` is the selected laser's TLS_SOURCES entry: its wl_min/wl_max
    bound the wavelengths and its power_rules bound the TLS power.
    """
    values = []
    for i, s in enumerate(raw_strings):
        if i == 3 and s.strip() == "":  # step_size defaults to 0 when empty
            values.append(0.0)
            continue
        try:
            values.append(float(s))
        except ValueError:
            return None, "all fields must be numbers."
    wav_start, wav_stop, sweep_speed, step_size, power_dbm = values[0], values[1], values[2], values[3], values[4]
    
    # wav_start    -= padding
    # wav_stop     += padding
    
    wl_min, wl_max = source_spec["wl_min"], source_spec["wl_max"]
    if not (wl_min <= wav_start <= wl_max) or not (wl_min <= wav_stop <= wl_max):
        return None, f"Wavelengths must be between {wl_min:g} and {wl_max:g} nm."
    if wav_start >= wav_stop:
        return None, "Start wavelength must be less than Stop wavelength."
    if step_size < 0:
        return None, "Step size must not be less than 0."
    if f"{sweep_speed}" not in SWEEP_SPEED_OPTIONS:
        return None, "Sweep speed must be selected from the dropdown list."
    # Maximum input power for N7748A: 16 dBm
    # TLS power: of the source's bands that contain the whole sweep, the one
    # with the highest limit applies (nested bands: tightest = highest). The
    # old if/elif chain fell through to a tighter band's *lower* limit when the
    # power was under the wider band's limit, rejecting 9-11 dBm in 1515-1620.
    applicable = [(lo, hi, lim) for lo, hi, lim in source_spec["power_rules"]
                  if lo <= wav_start and wav_stop <= hi]
    if applicable:
        lo, hi, lim = max(applicable, key=lambda rule: rule[2])
        if power_dbm > lim:
            return None, f"TLS power exceeds the maximum ({lim:g} dBm) in {lo:g}-{hi:g} nm"
    
    avg_t         = int(step_size/sweep_speed*1e3)  # us
    # 25 us <= avg_t <= 10s
    avg_t         = min(max(avg_t, 25), 10000000)
    step_new      = round((sweep_speed/1e3) * avg_t, 4)
    wav_range     = ((wav_stop + padding) - (wav_start - padding)) * 1000   # pm
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
    int() conversion so a bad preset value is reported instead of crashing — that
    includes padding_nm(), which validate_inputs depends on.
    """
    for label in (PADDING_LABEL, PM_RANGE_LABEL, DYN_SCAN_LABEL):
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
        lo_s = lo_s.strip() or "0" if lo_s.strip() != "inf" else "0"
        hi_s = hi_s.strip() or "0" if hi_s.strip() != "inf" else "0"
        try:
            lo, hi = float(lo_s), float(hi_s)
        except ValueError:
            return None, "all Pass/Fail Criteria fields must be numbers."
        if lo < 0 or hi < 0:
            return None, "Pass/Fail Criteria values must not be negative."
        if lo > 0 and hi == 0:
            hi = float("inf")
        if lo > hi:
            return None, f"{label}: min must not exceed max."
        values[label] = (lo, hi)
    return values, None


def validation_error(msg, result_label, num_data, avg_time, saved, run_btn):
    result_label.config(text=f"Error: {msg}", fg="red")
    saved["ok"] = False
    run_btn.config(state="disabled")
