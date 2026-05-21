import csv
import os
from datetime import datetime
import tkinter as tk
from prep_instruments import reset_inst

FIELD_LABELS = ["Start Wavelength (nm)", "Stop Wavelength (nm)", "Sweep Speed (nm/s)", "Step Size (pm)", "TLS Power (dBm)"]
DEFAULTS = ["0", "0", "0.5", "0.0125", "0.1"]

PRESET_CSV = "preset.csv"

PADDING = 50 # addtional padding in pm

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


def get_inputs(pm=None, laser=None):
    params = {}
    saved = {"ok": False}
    ran = {"ok": False}

    def on_save():
        values = []
        for entry in entries:
            try:
                values.append(float(entry.get()))
            except ValueError:
                result_label.config(text="Error: all fields must be numbers.")
                num_data.set("")
                avg_time.set("")
                saved["ok"] = False
                run_btn.config(state="disabled")
                return

        speed_tmp = values[2]   # nm/s
        step_tmp = values[3]    # pm

        at_tmp = int(step_tmp/speed_tmp*1e3)    # us
        at_tmp = 25 if at_tmp < 25 else at_tmp
        step_tmp = (speed_tmp/1e3) * at_tmp

        num_data_tmp = int((values[1] - values[0])/step_tmp*1e3) + 1

        num_data.set(f"{num_data_tmp}")
        avg_time.set(f"{at_tmp}")
        
        if step_tmp != float(entries[3].get()):
            entries[3].delete(0, tk.END)
            entries[3].insert(0, f"{step_tmp:.4f}")
            entries[3].config(fg="red")

        result_label.config(text="Saved. Review values, then click Run.")

        params["wav_start"]    = values[0]
        params["wav_stop"]     = values[1]
        params["sweep_speed"]  = values[2]
        params["step_size"]    = step_tmp
        params["tls_power"]    = values[4]
        params["num_data"]     = num_data_tmp
        params["avg_time"]     = at_tmp
        params["plot_backend"] = plot_backend_var.get()
        params["save_csv"]     = save_csv_var.get()
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        params["file_name"] = f"{file_name_var.get()}_{ts}{".csv"}"

        params["peak_csv"]       = save_csv_var2.get()
        params["peak_file_name"] = file_name_var2.get()+".csv"
        params["peak_label"]     = label2_var.get()
        params["peak_timestamp"] = ts

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
            entry.delete(0, tk.END)
            entry.insert(0, val)
        on_entry_change()

    def on_save_csv_change(*_):
        if save_csv_var.get() == "y":
            file_name_entry.config(state="normal")
        else:
            file_name_entry.config(state="disabled")
        on_entry_change()

    def on_save_csv2_change(*_):
        state = "normal" if save_csv_var2.get() == "y" else "disabled"
        file_name_entry2.config(state=state)
        label2_entry.config(state=state)
        on_entry_change()

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
        _last["save_csv"] = save_csv_var.get()
        _last["file_name"] = file_name_var.get()
        _last["peak_csv"]   = save_csv_var2.get()
        _last["peak_file_name"] = file_name_var2.get()
        _last["peak_label"] = label2_var.get()
        _last["plot_backend"]   = plot_backend_var.get()
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

    tk.Frame(frame, height=1, bg="gray").grid(row=N+3, column=0, columnspan=2, sticky="ew", pady=8)

    save_csv_var = tk.StringVar(value=_last.get("save_csv", "n"))
    tk.Label(frame, text="Save raw data to CSV?", anchor="w", width=22).grid(row=N+4, column=0, pady=4, sticky="w")
    tk.OptionMenu(frame, save_csv_var, "n", "y").grid(row=N+4, column=1, pady=4, sticky="w")
    save_csv_var.trace_add("write", on_save_csv_change)

    file_name_var = tk.StringVar(value=_last.get("file_name", ""))
    tk.Label(frame, text=" - CSV File name", anchor="w", width=22).grid(row=N+5, column=0, pady=4, sticky="w")
    file_name_entry = tk.Entry(frame, textvariable=file_name_var, width=20,
                               state="normal" if save_csv_var.get() == "y" else "disabled")
    file_name_entry.grid(row=N+5, column=1, pady=4)
    file_name_entry.bind("<Key>", on_entry_change)

    save_csv_var2 = tk.StringVar(value=_last.get("peak_csv", "n"))
    tk.Label(frame, text="Save peak analysis to CSV?", anchor="w", width=22).grid(row=N+6, column=0, pady=4, sticky="w")
    tk.OptionMenu(frame, save_csv_var2, "n", "y").grid(row=N+6, column=1, pady=4, sticky="w")
    save_csv_var2.trace_add("write", on_save_csv2_change)

    file_name_var2 = tk.StringVar(value=_last.get("peak_file_name", ""))
    tk.Label(frame, text=" - CSV File name", anchor="w", width=22).grid(row=N+7, column=0, pady=4, sticky="w")
    file_name_entry2 = tk.Entry(frame, textvariable=file_name_var2, width=20,
                                state="normal" if save_csv_var2.get() == "y" else "disabled")
    file_name_entry2.grid(row=N+7, column=1, pady=4)
    file_name_entry2.bind("<Key>", on_entry_change)

    label2_var = tk.StringVar(value=_last.get("peak_label", "none"))
    tk.Label(frame, text=" - Label", anchor="w", width=22).grid(row=N+8, column=0, pady=4, sticky="w")
    label2_entry = tk.Entry(frame, textvariable=label2_var, width=20,
                            state="normal" if save_csv_var2.get() == "y" else "disabled")
    label2_entry.grid(row=N+8, column=1, pady=4)
    label2_entry.bind("<Key>", on_entry_change)

    plot_backend_var = tk.StringVar(value=_last.get("plot_backend", "plotly"))
    tk.Label(frame, text="Backend for Plotting", anchor="w", width=22).grid(row=N+9, column=0, pady=4, sticky="w")
    tk.OptionMenu(frame, plot_backend_var, "matplotlib", "plotly").grid(row=N+9, column=1, pady=4, sticky="w")
    plot_backend_var.trace_add("write", on_entry_change)

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
        param = get_inputs()
        if not param:
            break
        print(param)
