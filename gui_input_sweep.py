from datetime import datetime
import tkinter as tk
from tkinter import ttk
import logging

from structs import Params
from gui_input_common import (
    FIELD_LABELS, DEFAULTS, SWEEP_SPEED_OPTIONS, PADDING,
    EXTRA_LABELS, EXTRA_DEFAULTS, PM_RANGE_LABEL, DYN_SCAN_LABEL, DECREMENT_LABEL,
    load_presets, save_preset, delete_preset, make_extra_widgets, validate_inputs, validate_extras, validate_dynamic_range, validation_error,
)

log = logging.getLogger(__name__)

_last = {}  # persists raw field values within one execution
# Persists across get_inputs() calls (the window is recreated each loop):
#   has_run   — at least one Run has happened this session
#   reference — current reference status (True/False)
_state = {"has_run": False, "reference": False}


def section_header(frame, text, row):
    """Place a bold section title plus a horizontal separator line below it."""
    tk.Label(frame, text=text, font=("TkDefaultFont", 10, "bold"), anchor="w").grid(
        row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))
    ttk.Separator(frame, orient="horizontal").grid(
        row=row + 1, column=0, columnspan=2, sticky="ew", pady=(0, 6))


def get_inputs():
    params = Params()
    params.reference = _state["reference"]
    saved = {"ok": False}
    ran = {"ok": False}

    def set_locked(locked):
        """Lock/unlock the parameter fields and toggle Save/Change/Run accordingly."""
        field_state = "disabled" if locked else "normal"
        preset_menu.config(state=field_state)
        for w in entry_widgets:
            w.config(state=field_state)
        extra_menus[PM_RANGE_LABEL].config(state=field_state)
        extra_menus[DYN_SCAN_LABEL].config(state=field_state)
        if locked:
            extra_menus[DECREMENT_LABEL].config(state="disabled")
        else:
            dec_state = "normal" if extra_vars[DYN_SCAN_LABEL].get() in ("2", "3") else "disabled"
            extra_menus[DECREMENT_LABEL].config(state=dec_state)
        save_btn.config(state="disabled" if locked else "normal")
        change_btn.config(state="normal" if locked else "disabled")
        preset_save_btn.config(state="normal" if locked else "disabled")
        run_btn.config(state="normal" if locked else "disabled")

    def on_save():
        values, error = validate_inputs([e.get() for e in entries], num_data, avg_time)
        if error:
            validation_error(error, result_label, num_data, avg_time, saved, run_btn)
            return

        extra_strs = {label: extra_vars[label].get() for label in EXTRA_LABELS}
        error = validate_extras(extra_strs)
        if error:
            validation_error(error, result_label, num_data, avg_time, saved, run_btn)
            return

        pm_range  = int(extra_strs[PM_RANGE_LABEL])
        dyn_scans = int(extra_strs[DYN_SCAN_LABEL])
        # Decrement is unused (and may be unvalidated) when only one scan runs.
        decrement = int(extra_strs[DECREMENT_LABEL]) if dyn_scans in (2, 3) else int(EXTRA_DEFAULTS[DECREMENT_LABEL])

        error = validate_dynamic_range(pm_range, dyn_scans, decrement)
        if error:
            validation_error(error, result_label, num_data, avg_time, saved, run_btn)
            return

        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        ds = datetime.now().strftime("%Y-%m-%d")

        params.wl_start   = values[0]
        params.wl_stop    = values[1]
        params.speed      = values[2]
        params.step_pm    = values[3]
        params.tls_dbm    = values[4]
        params.at_us      = values[5]
        params.num_data   = values[6]

        params.pm_range   = pm_range
        params.dyn_scans  = dyn_scans
        params.decrement  = decrement

        params.padding    = PADDING
        params.time       = ts
        params.date       = ds

        # If step size is adjusted, turn the field red
        if params.step_pm != float(entries[3].get()):
            entries[3].delete(0, tk.END)
            entries[3].insert(0, f"{params.step_pm:.4f}")
            entries[3].config(fg="red")

        result_label.config(text="Parameters saved. Review values, then click Run or press Enter.", fg="blue")

        saved["ok"] = True
        set_locked(True)

    def on_change_params():
        # Re-open the parameter fields for editing; require a fresh Save before Run.
        saved["ok"] = False
        set_locked(False)
        # Changing parameters invalidates any reference taken against them, and
        # resets the reference section to its pre-first-run state.
        _state["reference"] = False
        _state["has_run"] = False
        params.reference = False
        update_ref_ui()
        result_label.config(text="Parameters unlocked. Edit and Save again; the reference has been cleared.", fg="red")

    def on_entry_change(*args):
        # Enter doesn't modify the field — let it trigger Run instead of
        # invalidating the saved state. (Called from bind with an event, from
        # trace_add with 3 args, and directly with none.)
        event = args[0] if args else None
        if getattr(event, "keysym", "") in ("Return", "KP_Enter"):
            return
        entries[3].config(fg="black")
        # Invalidate save whenever any field is edited
        if saved["ok"]:
            saved["ok"] = False
            set_locked(False)
            result_label.config(text="Inputs changed — please Save again.", fg="red")

    def on_preset_change(*_):
        name = preset_var.get()
        if name == "none" or name not in presets:
            return
        vals = presets[name]
        for entry, label in zip(entries, FIELD_LABELS):
            if isinstance(entry, tk.StringVar):
                entry.set(vals[label])
            else:
                entry.delete(0, tk.END)
                entry.insert(0, vals[label])
        for label in EXTRA_LABELS:
            extra_vars[label].set(vals[label])
        on_entry_change()

    def on_run():
        if not saved["ok"]:
            return
        _last["fields"] = [e.get() for e in entries]
        _last["preset"] = preset_var.get()
        _last["extras"] = {label: extra_vars[label].get() for label in EXTRA_LABELS}

        ran["ok"] = True
        _state["has_run"] = True
        log.info("params: %s", params)
        result_label.config(text="Running...", fg="black")
        root.after(200, root.destroy)

    def on_save_preset():
        # Only reachable once parameters have passed Save's checks.
        if not saved["ok"]:
            return
        # Snapshot the current (validated) field values, keyed by CSV column.
        preset_vals = {label: entry.get() for entry, label in zip(entries, FIELD_LABELS)}
        for label in EXTRA_LABELS:
            preset_vals[label] = extra_vars[label].get()

        existing = load_presets()
        names = list(existing.keys())

        top = tk.Toplevel(root)
        top.title("Manage Presets")
        top.resizable(False, False)
        top.transient(root)
        top.grab_set()

        mode = tk.StringVar(value="replace" if names else "new")

        tk.Radiobutton(top, text="Replace a preset", variable=mode, value="replace",
                       state="normal" if names else "disabled").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))
        replace_var = tk.StringVar(value=names[0] if names else "")
        replace_menu = tk.OptionMenu(top, replace_var, *(names or [""]))
        replace_menu.grid(row=1, column=0, sticky="w", padx=34, pady=(0, 4))

        tk.Radiobutton(top, text="Create a new preset — enter a name\n(overwrites any existing preset of the same name)",
                       variable=mode, value="new", justify="left").grid(row=2, column=0, sticky="w", padx=10, pady=(6, 0))
        new_var = tk.StringVar()
        new_entry = tk.Entry(top, textvariable=new_var, width=32)
        new_entry.grid(row=3, column=0, sticky="w", padx=34, pady=(0, 4))

        tk.Radiobutton(top, text="Delete a preset", variable=mode, value="delete",
                       state="normal" if names else "disabled").grid(row=4, column=0, sticky="w", padx=10, pady=(6, 0))
        delete_var = tk.StringVar(value=names[0] if names else "")
        delete_menu = tk.OptionMenu(top, delete_var, *(names or [""]))
        delete_menu.grid(row=5, column=0, sticky="w", padx=34, pady=(0, 4))

        msg = tk.Label(top, text="", fg="red", wraplength=320, justify="left")
        msg.grid(row=6, column=0, padx=10)

        def sync_mode(*_):
            replace_menu.config(state="normal" if (mode.get() == "replace" and names) else "disabled")
            new_entry.config(state="normal" if mode.get() == "new" else "disabled")
            delete_menu.config(state="normal" if (mode.get() == "delete" and names) else "disabled")

        mode.trace_add("write", sync_mode)
        sync_mode()

        def remove_from_main_menu(name):
            menu = preset_menu["menu"]
            try:
                menu.delete(menu.index(name))
            except (tk.TclError, TypeError):
                pass
            if preset_var.get() == name:
                preset_var.set("none")

        def do_action():
            if mode.get() == "delete":
                name = delete_var.get().strip()
                if not name:
                    msg.config(text="No preset selected to delete.")
                    return
                error = delete_preset(name)
                if error:
                    msg.config(text=error)
                    return
                remove_from_main_menu(name)
                top.destroy()
                result_label.config(text=f"Preset '{name}' deleted.", fg="black")
                return

            if mode.get() == "replace":
                name = replace_var.get().strip()
                if not name:
                    msg.config(text="No existing preset to replace.")
                    return
            else:
                name = new_var.get().strip()
                if not name:
                    msg.config(text="Please enter a name.")
                    return

            error = save_preset(name, preset_vals)
            if error:
                msg.config(text=error)
                return

            # Surface a freshly added name in the main preset dropdown too.
            if name not in names:
                preset_menu["menu"].add_command(label=name, command=tk._setit(preset_var, name))
            top.destroy()
            result_label.config(text=f"Preset '{name}' saved.", fg="black")

        tk.Button(top, text="Save/Delete", command=do_action, width=12).grid(row=7, column=0, pady=10)

        new_entry.focus_set()

    def update_ref_ui():
        if _state["reference"]:
            status_value.config(text="Set", fg="red")
        else:
            status_value.config(text="Not Set", fg="black")
        set_ref_btn.config(state="normal" if _state["has_run"] else "disabled")
        del_ref_btn.config(state="normal" if _state["reference"] else "disabled")

    def on_set_ref():
        _state["reference"] = True
        params.reference = True
        update_ref_ui()

    def on_del_ref():
        _state["reference"] = False
        params.reference = False
        update_ref_ui()

    root = tk.Tk()
    root.title("Test Configuration")
    root.resizable(False, False)

    frame = tk.Frame(root, padx=20, pady=15)
    frame.pack()

    N = len(FIELD_LABELS)

    # ---- Grid row layout -------------------------------------------------
    FIELDS_START = 2                     # preset at FIELDS_START, fields at FIELDS_START+1..+N
    EXTRAS_START = FIELDS_START + N + 1   # rows for the three extra dropdowns
    LOGCOUNT_ROW = EXTRAS_START + 3
    AVGTIME_ROW  = LOGCOUNT_ROW + 1
    SAVEBTN_ROW  = AVGTIME_ROW + 1
    HEADER2_ROW  = SAVEBTN_ROW + 1
    RUNBTN_ROW   = HEADER2_ROW + 2   # +2 leaves room for the separator line
    HEADER3_ROW  = RUNBTN_ROW + 1
    REFBTN_ROW   = HEADER3_ROW + 2
    RESULT_ROW   = REFBTN_ROW + 1

    # ---- Set Parameters --------------------------------------------------
    section_header(frame, "Parameters", 0)

    presets = load_presets()
    preset_options = ["none"] + list(presets.keys())
    preset_var = tk.StringVar(value=_last.get("preset", "none"))
    tk.Label(frame, text="Load Preset", anchor="w", width=22).grid(row=FIELDS_START, column=0, pady=4, sticky="w")
    preset_menu = tk.OptionMenu(frame, preset_var, *preset_options)
    preset_menu.grid(row=FIELDS_START, column=1, pady=4, sticky="w")
    preset_var.trace_add("write", on_preset_change)

    init_fields = _last.get("fields", DEFAULTS)
    entries = []
    entry_widgets = []
    for i, (label_text, default) in enumerate(zip(FIELD_LABELS, init_fields)):
        tk.Label(frame, text=label_text, anchor="w", width=22).grid(row=FIELDS_START+i+1, column=0, pady=4, sticky="w")
        if i == 2:  # Sweep Speed — dropdown
            sv = tk.StringVar(value=default if default in SWEEP_SPEED_OPTIONS else SWEEP_SPEED_OPTIONS[0])
            menu = tk.OptionMenu(frame, sv, *SWEEP_SPEED_OPTIONS)
            menu.grid(row=FIELDS_START+i+1, column=1, pady=4, sticky="w")
            sv.trace_add("write", on_entry_change)
            entries.append(sv)
            entry_widgets.append(menu)
        else:
            e = tk.Entry(frame, width=20)
            e.insert(0, default)
            e.grid(row=FIELDS_START+i+1, column=1, pady=4, sticky="w")
            e.bind("<Key>", on_entry_change)
            entries.append(e)
            entry_widgets.append(e)

    init_extras = _last.get("extras", EXTRA_DEFAULTS)
    extra_vars, extra_menus = make_extra_widgets(frame, EXTRAS_START, init_extras, on_entry_change)

    num_data = tk.StringVar()
    avg_time = tk.StringVar()

    tk.Label(frame, text="Log Count / Sweep", anchor="w", width=25).grid(row=LOGCOUNT_ROW, column=0, sticky="w", pady=4)
    tk.Label(frame, textvariable=num_data, anchor="w").grid(row=LOGCOUNT_ROW, column=1, sticky="w", pady=4)

    tk.Label(frame, text="Averaging Time (μs)", anchor="w", width=22).grid(row=AVGTIME_ROW, column=0, sticky="w", pady=4)
    tk.Label(frame, textvariable=avg_time, anchor="w").grid(row=AVGTIME_ROW, column=1, sticky="w", pady=4)

    save_frame = tk.Frame(frame)
    save_frame.grid(row=SAVEBTN_ROW, column=0, columnspan=2, pady=10)
    save_btn = tk.Button(save_frame, text="Save", command=on_save, width=10)
    save_btn.pack(side="left", padx=5)
    change_btn = tk.Button(save_frame, text="Change", command=on_change_params, width=10, state="disabled")
    change_btn.pack(side="left", padx=5)
    preset_save_btn = tk.Button(save_frame, text="Manage Presets...", command=on_save_preset, state="disabled")
    preset_save_btn.pack(side="left", padx=5)

    # ---- Instruments -----------------------------------------------------
    section_header(frame, "Instruments", HEADER2_ROW)
    run_btn = tk.Button(frame, text="Run", command=on_run, width=10, state="disabled")
    run_btn.grid(row=RUNBTN_ROW, column=0, columnspan=2, pady=10)

    # ---- Reference -------------------------------------------------------
    # Status sits next to the section title instead of in its own field.
    ref_header = tk.Frame(frame)
    ref_header.grid(row=HEADER3_ROW, column=0, columnspan=2, sticky="w", pady=(10, 0))
    tk.Label(ref_header, text="Reference", font=("TkDefaultFont", 10, "bold")).pack(side="left")
    status_value = tk.Label(ref_header, text="Not Set", fg="black")
    status_value.pack(side="left", padx=(8, 0))
    ttk.Separator(frame, orient="horizontal").grid(
        row=HEADER3_ROW + 1, column=0, columnspan=2, sticky="ew", pady=(0, 6))

    ref_frame = tk.Frame(frame)
    ref_frame.grid(row=REFBTN_ROW, column=0, columnspan=2, pady=4)
    set_ref_btn = tk.Button(ref_frame, text="Set as Reference", command=on_set_ref, state="disabled")
    set_ref_btn.pack(side="left", padx=5)
    del_ref_btn = tk.Button(ref_frame, text="Delete Reference", command=on_del_ref, state="disabled")
    del_ref_btn.pack(side="left", padx=5)

    # Enter triggers Run when it's enabled (on_run is a no-op until saved).
    root.bind("<Return>", lambda _e: on_run())
    root.bind("<KP_Enter>", lambda _e: on_run())

    result_label = tk.Label(frame, text="", wraplength=320, justify="left")
    result_label.grid(row=RESULT_ROW, column=0, columnspan=2)

    update_ref_ui()

    # Reopening with values from a previous run: auto-save so Run is ready
    # without pressing Save again. This also re-locks the parameter fields,
    # keeping the locked state across loops.
    if "fields" in _last:
        on_save()

    # Grab keyboard focus so Enter works without clicking the window first
    # (on reopen, focus tends to stay on the console).
    root.lift()
    root.attributes("-topmost", True)
    root.after(0, lambda: root.attributes("-topmost", False))
    root.after(0, root.focus_force)

    root.mainloop()
    return params if ran["ok"] else None


if __name__ == "__main__":
    while True:
        params = get_inputs()
        if not params:
            break
        print(params)
