import csv
from datetime import datetime
import tkinter as tk

from structs import Params
from prep_instruments import reset_inst

FIELD_LABELS = ["Start Wavelength (nm)", "Stop Wavelength (nm)", "Sweep Speed (nm/s)", "Step Size (pm)", "TLS Power (dBm)"]
DEFAULTS = ["0", "0", "0.5", "0.0125", "0.1"]
SWEEP_SPEED_OPTIONS = ["0.5", "1.0", "2.0", "5.0", "10.0", "20.0", "40.0", "50.0", "80.0", "100.0", "150.0", "160.0", "200.0"]

PRESET_CSV = "preset.csv"

PADDING = 0.050 # addtional padding in nm

_last = {}  # persists raw field values within one execution

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


WAV_MIN, WAV_MAX = 1450+PADDING, 1650-PADDING

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


def get_inputs(pm=None, laser=None):
    params = Params()
    saved = {"ok": False}
    ran = {"ok": False}

    def on_save():
        values, error = validate_inputs([e.get() for e in entries])
        if error:
            validation_error(error, result_label, num_data, avg_time, saved, run_btn)
            return

        wav_start = values[0] - PADDING  # nm
        wav_stop  = values[1] + PADDING  # nm
        speed     = values[2]            # nm/s
        step_new  = values[3]            # pm

        avg_t        = int(step_new/speed*1e3)        # us
        avg_t        = 25 if avg_t < 25 else avg_t
        step_new     = round((speed/1e3) * avg_t, 4)
        wav_range    = (wav_stop - wav_start) * 1000  # pm
        pp           = int(wav_range // step_new)
        qq           = wav_range % step_new
        num_data_log = pp if qq == 0 else pp+1

        num_data.set(f"{num_data_log}")
        avg_time.set(f"{avg_t}")
        
        # If step size is adjusted, turn the field red
        if step_new != float(entries[3].get()):
            entries[3].delete(0, tk.END)
            entries[3].insert(0, f"{step_new:.4f}")
            entries[3].config(fg="red")

        result_label.config(text="Saved. Review values, then click Run.")

        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        ds = datetime.now().strftime("%Y-%m-%d")

        params.wl_start   = values[0]
        params.wl_stop    = values[1]
        params.speed      = values[2]
        params.step_pm    = step_new
        params.tls_dbm    = values[4]
        params.num_data   = num_data_log
        params.at_us      = avg_t
        params.padding    = PADDING
        # params.csv        = save_csv_var.get()
        # params.csv_fname  = f"{file_name_var.get()}_{ts}{".csv"}"
        # params.peak_csv   = save_csv_var2.get()
        # params.peak_fname = file_name_var2.get()+".csv"
        # params.peak_label = label2_var.get()
        params.time       = ts
        params.date       = ds
        
        saved["ok"] = True
        run_btn.config(state="normal")

    def on_entry_change(*_):
        entries[3].config(fg="black")
        # Invalidate save whenever any field is edited
        if saved["ok"]:
            saved["ok"] = False
            run_btn.config(state="disabled")
            result_label.config(text="Inputs changed — please Save again.")

    def on_preset_change(*_):
        name = preset_var.get()
        if name == "none" or name not in presets:
            return
        for entry, val in zip(entries, presets[name]):
            if isinstance(entry, tk.StringVar):
                entry.set(val)
            else:
                entry.delete(0, tk.END)
                entry.insert(0, val)
        on_entry_change()

    # def on_save_csv_change(*_):
    #     if save_csv_var.get() == "y":
    #         file_name_entry.config(state="normal")
    #     else:
    #         file_name_entry.config(state="disabled")
    #     on_entry_change()

    # def on_save_csv2_change(*_):
    #     state = "normal" if save_csv_var2.get() == "y" else "disabled"
    #     file_name_entry2.config(state=state)
    #     label2_entry.config(state=state)
    #     on_entry_change()

    def on_reset():
        result_label.config(text="Resetting instruments...")
        root.update()
        reset_inst(pm, laser)
        result_label.config(text="Reset complete.")

    def on_run():
        if not saved["ok"]:
            return
        _last["fields"] = [e.get() for e in entries]
        _last["preset"] = preset_var.get()
        # _last["save_csv"] = save_csv_var.get()
        # _last["file_name"] = file_name_var.get()
        # _last["peak_csv"]   = save_csv_var2.get()
        # _last["peak_file_name"] = file_name_var2.get()
        # _last["peak_label"] = label2_var.get()
        # _last["plot_backend"]   = plot_backend_var.get()
        ran["ok"] = True
        result_label.config(text="Running...")
        root.after(200, root.destroy)

    root = tk.Tk()
    root.title("Test Configuration")
    root.resizable(False, False)

    frame = tk.Frame(root, padx=20, pady=15)
    frame.pack()

    N = len(FIELD_LABELS)

    presets = load_presets()
    preset_options = ["none"] + list(presets.keys())
    preset_var = tk.StringVar(value=_last.get("preset", "none"))
    tk.Label(frame, text="Preset?", anchor="w", width=22).grid(row=0, column=0, pady=4, sticky="w")
    tk.OptionMenu(frame, preset_var, *preset_options).grid(row=0, column=1, pady=4, sticky="w")
    preset_var.trace_add("write", on_preset_change)

    init_fields = _last.get("fields", DEFAULTS)
    entries = []
    for i, (label_text, default) in enumerate(zip(FIELD_LABELS, init_fields)):
        tk.Label(frame, text=label_text, anchor="w", width=22).grid(row=i+1, column=0, pady=4, sticky="w")
        if i == 2:  # Sweep Speed — dropdown
            sv = tk.StringVar(value=default if default in SWEEP_SPEED_OPTIONS else SWEEP_SPEED_OPTIONS[0])
            tk.OptionMenu(frame, sv, *SWEEP_SPEED_OPTIONS).grid(row=i+1, column=1, pady=4, sticky="w")
            sv.trace_add("write", on_entry_change)
            entries.append(sv)
        else:
            e = tk.Entry(frame, width=20)
            e.insert(0, default)
            e.grid(row=i+1, column=1, pady=4)
            e.bind("<Key>", on_entry_change)
            entries.append(e)

    num_data = tk.StringVar()
    avg_time = tk.StringVar()

    tk.Label(frame, text="Number of data to be logged", anchor="w", width=25).grid(row=N+1, column=0, sticky="w", pady=4)
    tk.Entry(frame, textvariable=num_data, state="readonly", width=20).grid(row=N+1, column=1, pady=4)

    tk.Label(frame, text="Averaging Time (\u03BCs)", anchor="w", width=22).grid(row=N+2, column=0, sticky="w", pady=4)
    tk.Entry(frame, textvariable=avg_time, state="readonly", width=20).grid(row=N+2, column=1, pady=4)

    # tk.Frame(frame, height=1, bg="gray").grid(row=N+3, column=0, columnspan=2, sticky="ew", pady=8)

    # save_csv_var = tk.StringVar(value=_last.get("save_csv", "n"))
    # tk.Label(frame, text="Save raw data to CSV?", anchor="w", width=22).grid(row=N+4, column=0, pady=4, sticky="w")
    # tk.OptionMenu(frame, save_csv_var, "n", "y").grid(row=N+4, column=1, pady=4, sticky="w")
    # save_csv_var.trace_add("write", on_save_csv_change)

    # file_name_var = tk.StringVar(value=_last.get("file_name", ""))
    # tk.Label(frame, text=" - CSV File name", anchor="w", width=22).grid(row=N+5, column=0, pady=4, sticky="w")
    # file_name_entry = tk.Entry(frame, textvariable=file_name_var, width=20,
    #                            state="normal" if save_csv_var.get() == "y" else "disabled")
    # file_name_entry.grid(row=N+5, column=1, pady=4)
    # file_name_entry.bind("<Key>", on_entry_change)

    # save_csv_var2 = tk.StringVar(value=_last.get("peak_csv", "n"))
    # tk.Label(frame, text="Save peak analysis to CSV?", anchor="w", width=22).grid(row=N+6, column=0, pady=4, sticky="w")
    # tk.OptionMenu(frame, save_csv_var2, "n", "y").grid(row=N+6, column=1, pady=4, sticky="w")
    # save_csv_var2.trace_add("write", on_save_csv2_change)

    # file_name_var2 = tk.StringVar(value=_last.get("peak_file_name", ""))
    # tk.Label(frame, text=" - CSV File name", anchor="w", width=22).grid(row=N+7, column=0, pady=4, sticky="w")
    # file_name_entry2 = tk.Entry(frame, textvariable=file_name_var2, width=20,
    #                             state="normal" if save_csv_var2.get() == "y" else "disabled")
    # file_name_entry2.grid(row=N+7, column=1, pady=4)
    # file_name_entry2.bind("<Key>", on_entry_change)

    # label2_var = tk.StringVar(value=_last.get("peak_label", "none"))
    # tk.Label(frame, text=" - Label", anchor="w", width=22).grid(row=N+8, column=0, pady=4, sticky="w")
    # label2_entry = tk.Entry(frame, textvariable=label2_var, width=20,
    #                         state="normal" if save_csv_var2.get() == "y" else "disabled")
    # label2_entry.grid(row=N+8, column=1, pady=4)
    # label2_entry.bind("<Key>", on_entry_change)

    # plot_backend_var = tk.StringVar(value=_last.get("plot_backend", "plotly"))
    # tk.Label(frame, text="Backend for Plotting", anchor="w", width=22).grid(row=N+9, column=0, pady=4, sticky="w")
    # tk.OptionMenu(frame, plot_backend_var, "matplotlib", "plotly").grid(row=N+9, column=1, pady=4, sticky="w")
    # plot_backend_var.trace_add("write", on_entry_change)

    btn_frame = tk.Frame(frame)
    btn_frame.grid(row=N+10, column=0, columnspan=2, pady=10)
    tk.Button(btn_frame, text="Save", command=on_save, width=10).pack(side="left", padx=5)
    run_btn = tk.Button(btn_frame, text="Run", command=on_run, width=10, state="disabled")
    run_btn.pack(side="left", padx=5)
    tk.Button(btn_frame, text="Reset", command=on_reset, width=10).pack(side="left", padx=5)

    result_label = tk.Label(frame, text="")
    result_label.grid(row=N+11, column=0, columnspan=2)

    root.mainloop()
    return params if ran["ok"] else None


if __name__ == "__main__":
    while True:
        params = get_inputs()
        if not params:
            break
        print(params)
