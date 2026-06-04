from datetime import datetime
import tkinter as tk

from structs import Params
from gui_input_common import (
    FIELD_LABELS, DEFAULTS, SWEEP_SPEED_OPTIONS, PADDING,
    load_presets, validate_inputs, validation_error,
)

_last = {}  # persists raw field values within one execution
saved_reference = False  # True once a reference sweep has been run; persists across get_inputs() calls


def get_inputs():
    params = Params()
    saved = {"ok": False}
    ran = {"ok": False}
    state = {"new_ref": False}  # True while the user is defining a fresh reference

    def compute_and_fill(sweep_type):
        """Validate the entries, fill `params`, update the readout. Returns True on success."""
        values, error = validate_inputs([e.get() for e in entries])
        if error:
            validation_error(error, result_label, num_data, avg_time, saved, run_btn)
            return False

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
        params.time       = ts
        params.date       = ds
        params.sweep      = sweep_type
        return True

    def on_save():
        if not compute_and_fill("reference"):
            return
        result_label.config(text="Saved. Review values, then click Run.")
        saved["ok"] = True
        run_btn.config(state="normal")

    def on_new_reference():
        global saved_reference
        saved_reference = False        # discard the old reference — "New reference resets all"
        state["new_ref"] = True
        saved["ok"] = False
        set_fields_state("normal")
        save_btn.config(state="normal")
        run_btn.config(state="disabled")
        num_data.set("")
        avg_time.set("")
        result_label.config(text="Enter reference parameters, then click Save.")

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

    def on_run():
        global saved_reference
        if state["new_ref"]:
            # Running a freshly defined reference — requires a successful Save first.
            if not saved["ok"]:
                return
            saved_reference = True       # params already filled as "reference" by on_save
        else:
            # Running a cell measurement against the existing, locked reference.
            if not compute_and_fill("cell"):
                return
        _last["fields"] = [e.get() for e in entries]
        _last["preset"] = preset_var.get()
        
        ran["ok"] = True
        result_label.config(text="Running...")
        root.after(200, root.destroy)

    root = tk.Tk()
    root.title("Test Configuration")
    root.resizable(False, False)

    top = tk.Frame(root, padx=20)
    top.pack(fill="x", pady=(15, 0))
    tk.Button(top, text="New reference", command=on_new_reference, width=14).pack(anchor="w")

    frame = tk.Frame(root, padx=20, pady=15)
    frame.pack()

    N = len(FIELD_LABELS)

    field_widgets = []  # widgets locked/unlocked together (preset + parameter inputs)

    presets = load_presets()
    preset_options = ["none"] + list(presets.keys())
    preset_var = tk.StringVar(value=_last.get("preset", "none"))
    tk.Label(frame, text="Preset?", anchor="w", width=22).grid(row=0, column=0, pady=4, sticky="w")
    preset_menu = tk.OptionMenu(frame, preset_var, *preset_options)
    preset_menu.grid(row=0, column=1, pady=4, sticky="w")
    preset_var.trace_add("write", on_preset_change)
    field_widgets.append(preset_menu)

    init_fields = _last.get("fields", DEFAULTS)
    entries = []
    for i, (label_text, default) in enumerate(zip(FIELD_LABELS, init_fields)):
        tk.Label(frame, text=label_text, anchor="w", width=22).grid(row=i+1, column=0, pady=4, sticky="w")
        if i == 2:  # Sweep Speed — dropdown
            sv = tk.StringVar(value=default if default in SWEEP_SPEED_OPTIONS else SWEEP_SPEED_OPTIONS[0])
            menu = tk.OptionMenu(frame, sv, *SWEEP_SPEED_OPTIONS)
            menu.grid(row=i+1, column=1, pady=4, sticky="w")
            sv.trace_add("write", on_entry_change)
            entries.append(sv)
            field_widgets.append(menu)
        else:
            e = tk.Entry(frame, width=20)
            e.insert(0, default)
            e.grid(row=i+1, column=1, pady=4)
            e.bind("<Key>", on_entry_change)
            entries.append(e)
            field_widgets.append(e)

    def set_fields_state(s):
        for w in field_widgets:
            w.config(state=s)

    num_data = tk.StringVar()
    avg_time = tk.StringVar()

    tk.Label(frame, text="Number of data to be logged", anchor="w", width=25).grid(row=N+1, column=0, sticky="w", pady=4)
    tk.Entry(frame, textvariable=num_data, state="readonly", width=20).grid(row=N+1, column=1, pady=4)

    tk.Label(frame, text="Averaging Time (\u03BCs)", anchor="w", width=22).grid(row=N+2, column=0, sticky="w", pady=4)
    tk.Entry(frame, textvariable=avg_time, state="readonly", width=20).grid(row=N+2, column=1, pady=4)

    btn_frame = tk.Frame(frame)
    btn_frame.grid(row=N+10, column=0, columnspan=2, pady=10)
    save_btn = tk.Button(btn_frame, text="Save", command=on_save, width=10)
    save_btn.pack(side="left", padx=5)
    run_btn = tk.Button(btn_frame, text="Run", command=on_run, width=10, state="disabled")
    run_btn.pack(side="left", padx=5)

    result_label = tk.Label(frame, text="")
    result_label.grid(row=N+11, column=0, columnspan=2)

    # Initial state. Parameter fields and Save start locked; only New reference is usable.
    set_fields_state("disabled")
    save_btn.config(state="disabled")
    if saved_reference:
        # A reference already exists — allow measuring against it without re-entering parameters.
        run_btn.config(state="normal")
        result_label.config(text="Reference set. Click Run to measure, or New reference to start over.")
    else:
        run_btn.config(state="disabled")
        result_label.config(text="Click New reference to begin.")

    root.mainloop()
    return params if ran["ok"] else None


if __name__ == "__main__":
    while True:
        params = get_inputs()
        if not params:
            break
        print(params)
