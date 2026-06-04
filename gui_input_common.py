import csv

FIELD_LABELS = ["Start Wavelength (nm)", "Stop Wavelength (nm)", "Sweep Speed (nm/s)", "Step Size (pm)", "TLS Power (dBm)"]
DEFAULTS = ["0", "0", "0.5", "0.0125", "0.1"]
SWEEP_SPEED_OPTIONS = ["0.5", "1.0", "2.0", "5.0", "10.0", "20.0", "40.0", "50.0", "80.0", "100.0", "150.0", "160.0", "200.0"]

PRESET_CSV = "preset.csv"

PADDING = 0.050  # addtional padding in nm

WAV_MIN, WAV_MAX = 1450 + PADDING, 1650 - PADDING


def load_presets():
    """Return {material: [val, ...]} from preset.csv, or {} on any failure."""
    try:
        with open(PRESET_CSV, newline="") as f:
            reader = csv.DictReader(f)
            presets = {}
            for row in reader:
                name = row.get("Name", "").strip()
                if not name:
                    continue
                presets[name] = [row[label].strip() for label in FIELD_LABELS]
        return presets
    except Exception:
        return {}


def validate_inputs(raw_strings):
    """Return (values, None) on success or (None, error_msg) on failure."""
    values = []
    for s in raw_strings:
        try:
            values.append(float(s))
        except ValueError:
            return None, "all fields must be numbers."
    wav_start, wav_stop, sweep_speed, step_size, power_dbm = values[0], values[1], values[2], values[3], values[4]
    if not (WAV_MIN <= wav_start <= WAV_MAX) or not (WAV_MIN <= wav_stop <= WAV_MAX):
        return None, f"Wavelengths must be between {WAV_MIN} and {WAV_MAX} nm."
    if wav_start >= wav_stop:
        return None, "Start wavelength must be less than Stop wavelength."
    if step_size <= 0:
        return None, "Step size must be greater than 0."
    if f"{sweep_speed}" not in SWEEP_SPEED_OPTIONS:
        return None, "Sweep speed must be selected from the dropdown list."
    return values, None


def validation_error(msg, result_label, num_data, avg_time, saved, run_btn):
    result_label.config(text=f"Error: {msg}")
    num_data.set("")
    avg_time.set("")
    saved["ok"] = False
    run_btn.config(state="disabled")
