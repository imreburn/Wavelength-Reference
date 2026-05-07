import csv
import tkinter as tk

FIELD_LABELS = ["Start Wavelength (nm)", "Stop Wavelength (nm)", "Sweep Speed (nm/s)", "TLS Power (dBm)", "Averaging Time (us)"]
DEFAULTS = ["0", "0", "0", "0.1", "25"]

PRESET_CSV = "preset.csv"


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


def get_inputs():
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
                lambda_space.set("")
                saved["ok"] = False
                run_btn.config(state="disabled")
                return

        num_data_tmp = int(((values[1] - values[0]) / values[2]) / (values[4] / 1e6))
        lambda_space_tmp = ((values[1] - values[0]) / num_data_tmp) * 1e3

        num_data.set(f"{num_data_tmp}")
        lambda_space.set(f"{lambda_space_tmp:.4f}")
        result_label.config(text="Saved. Review values, then click Run.")

        params["wav_start"]    = values[0] * 1e-9
        params["wav_stop"]     = values[1] * 1e-9
        params["sweep_speed"]  = values[2] * 1e-9
        params["tls_power"]    = values[3]
        params["avg_time"]     = values[4] * 1e-6
        params["num_data"]     = num_data_tmp
        params["lambda_space"] = lambda_space_tmp
        params["save_csv"]     = save_csv_var.get()
        params["file_name"]    = file_name_var.get()

        saved["ok"] = True
        run_btn.config(state="normal")

    def on_entry_change(*_):
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

    def on_run():
        if not saved["ok"]:
            return
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
    preset_var = tk.StringVar(value="none")
    tk.Label(frame, text="Preset?", anchor="w", width=22).grid(row=0, column=0, pady=4, sticky="w")
    tk.OptionMenu(frame, preset_var, *preset_options).grid(row=0, column=1, pady=4, sticky="w")
    preset_var.trace_add("write", on_preset_change)

    entries = []
    for i, (label_text, default) in enumerate(zip(FIELD_LABELS, DEFAULTS)):
        tk.Label(frame, text=label_text, anchor="w", width=22).grid(row=i+1, column=0, pady=4, sticky="w")
        e = tk.Entry(frame, width=20)
        e.insert(0, default)
        e.grid(row=i+1, column=1, pady=4)
        e.bind("<Key>", on_entry_change)
        entries.append(e)

    save_csv_var = tk.StringVar(value="n")
    tk.Label(frame, text="Save result to CSV?", anchor="w", width=22).grid(row=N+1, column=0, pady=4, sticky="w")
    tk.OptionMenu(frame, save_csv_var, "n", "y").grid(row=N+1, column=1, pady=4, sticky="w")
    save_csv_var.trace_add("write", on_save_csv_change)

    file_name_var = tk.StringVar(value=".csv")
    tk.Label(frame, text="File name", anchor="w", width=22).grid(row=N+2, column=0, pady=4, sticky="w")
    file_name_entry = tk.Entry(frame, textvariable=file_name_var, width=20, state="disabled")
    file_name_entry.grid(row=N+2, column=1, pady=4)
    file_name_entry.bind("<Key>", on_entry_change)

    btn_frame = tk.Frame(frame)
    btn_frame.grid(row=N+3, column=0, columnspan=2, pady=10)
    tk.Button(btn_frame, text="Save", command=on_save, width=10).pack(side="left", padx=5)
    run_btn = tk.Button(btn_frame, text="Run", command=on_run, width=10, state="disabled")
    run_btn.pack(side="left", padx=5)

    result_label = tk.Label(frame, text="")
    result_label.grid(row=N+4, column=0, columnspan=2)

    separator = tk.Frame(frame, height=1, bg="gray")
    separator.grid(row=N+5, column=0, columnspan=2, sticky="ew", pady=8)

    num_data = tk.StringVar()
    lambda_space = tk.StringVar()

    tk.Label(frame, text="Number of data to be logged", anchor="w", width=25).grid(row=N+6, column=0, sticky="w")
    tk.Entry(frame, textvariable=num_data, state="readonly", width=20).grid(row=N+6, column=1)

    tk.Label(frame, text="Lambda spacing (pm)", anchor="w", width=22).grid(row=N+7, column=0, sticky="w", pady=4)
    tk.Entry(frame, textvariable=lambda_space, state="readonly", width=20).grid(row=N+7, column=1, pady=4)

    root.mainloop()
    return params if ran["ok"] else None


if __name__ == "__main__":
    param = get_inputs()
    print(param)
