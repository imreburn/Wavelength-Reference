from datetime import datetime
import math
import time
import tkinter as tk
from tkinter import ttk
import logging
import decimal

# Set Windows DPI awareness before the first Tk() window is created (import-time
# side effect). Must come before any tkinter window in the process.
import dpi_awareness  # noqa: F401

log = logging.getLogger(__name__)

from inst_helper import prep_inst, check_inst
from shutdown import IDLE_SECONDS, IDLE_POLL_MS
from structs import Params
from config_helper import (
    FIELD_LABELS, DEFAULTS, SWEEP_SPEED_OPTIONS, PADDING,
    EXTRA_LABELS, EXTRA_DEFAULTS, PM_RANGE_LABEL, DYN_SCAN_LABEL, DECREMENT_LABEL,
    CHANNEL_LABEL, CHANNEL_OPTIONS, CHANNEL_DEFAULT, channels_to_str, parse_channels,
    PASSFAIL_LABELS, PASSFAIL_KEYS, PASSFAIL_DEFAULT, PASSFAIL_COLUMNS, passfail_col,
    load_presets, save_preset, delete_preset, make_extra_widgets, validate_inputs, validate_extras, validate_passfail, validation_error,
)



_last = {}  # persists raw field values within one execution

# Fixed on-screen position for the window at first launch (top-left x, y).
WINDOW_POS = (50, 10)

# Persists across get_inputs() calls (the window is recreated each loop):
#   has_run   — at least one Run has happened this session
#   reference — current reference status (True/False)
#   pos       — last window position (x, y); None until first close, then
#               tracks wherever the user moved it
_state = {"has_run": False, "reference": False, "pos": None}


def _is_disabled(widget):
    """True if `widget` is a disabled Tk widget. False for anything stateless."""
    try:
        return str(widget.cget("state")) == "disabled"
    except (AttributeError, tk.TclError):
        return False


def section_header(frame, text, row):
    """Place a bold section title plus a horizontal separator line below it."""
    tk.Label(frame, text=text, font=("TkDefaultFont", 10, "bold"), anchor="w").grid(
        row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))
    ttk.Separator(frame, orient="horizontal").grid(
        row=row + 1, column=0, columnspan=2, sticky="ew", pady=(0, 6))


def get_inputs(pm=None, laser=None, auto_run=False):
    # auto_run: re-run the previous sweep without manual interaction (set by the
    # plot window's Repeat button). It is a control flag only — never stored on
    # Params, which holds run parameters exclusively.
    params = Params()
    params.reference = _state["reference"]
    saved = {"ok": False}
    ran = {"ok": False}
    # Cleanup for the power-readout window, if one is open. Set while the readout
    # window exists so root teardown (Run/Close) can cancel its pending `after`
    # refresh loop before destroying it — otherwise queued callbacks fire against
    # the destroyed widget ("invalid command name ...refresh").
    _readout = {"close": None}
    # Pending id of the idle-timeout poll below, so root teardown (Run/Close) can
    # cancel it for the same reason. Without this the poll survives destroy() on
    # Windows and fires against the deleted callback ("invalid command name
    # ..._check_idle"); the exact route has not been pinned down, so the
    # winfo_exists() guard in _check_idle stays as a second line of defence.
    _idle_job = {"id": None}

    def _cancel_idle():
        if _idle_job["id"]:
            root.after_cancel(_idle_job["id"])
            _idle_job["id"] = None

    def set_locked(locked):
        """Lock/unlock the parameter fields and toggle Save/Change/Run accordingly."""
        field_state = "disabled" if locked else "normal"
        preset_menu.config(state=field_state)
        for w in entry_widgets:
            w.config(state=field_state)
        for w in passfail_widgets:
            w.config(state=field_state)
        for cb in channel_checks:
            cb.config(state=field_state)
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
        read_pm_btn.config(state="normal" if locked else "disabled")

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

        channels = tuple(ch for ch in CHANNEL_OPTIONS if channel_vars[ch].get())
        if not channels:
            validation_error("at least one channel must be selected.", result_label, num_data, avg_time, saved, run_btn)
            return

        pf_raw = {label: (mn.get(), mx.get()) for label, (mn, mx) in passfail_entries.items()}
        pf_values, error = validate_passfail(pf_raw)
        if error:
            validation_error(error, result_label, num_data, avg_time, saved, run_btn)
            return

        ts = datetime.now().strftime("%m/%d/%Y_%H-%M-%S")
        ds = datetime.now().strftime("%m/%d/%Y")

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
        params.channel    = channels

        for label, (lo_key, hi_key) in PASSFAIL_KEYS.items():
            lo, hi = pf_values[label]
            setattr(params, lo_key, lo)
            setattr(params, hi_key, hi)

        params.padding    = PADDING
        params.time       = ts
        params.date       = ds
        params.name       = "unknown" if preset_var.get() == "none" else preset_var.get()

        # If step size is adjusted, change the field color
        step_adjusted = ""
        if params.step_pm != float(entries[3].get()):
            entries[3].delete(0, tk.END)
            entries[3].insert(0, f"{params.step_pm:.4f}")
            entries[3].config(disabledforeground="#cc7a00")
            step_adjusted = "Step size is adjusted."
        else:
            # Clear any red left over from a previous adjustment.
            entries[3].config(fg="black", disabledforeground=default_disabledfg)

        result_label.config(text="Parameters saved. Review values, then click Run or press Enter. " + step_adjusted, fg="blue")

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
        # A disabled Entry keeps focus and still receives <Key> events (it just
        # won't insert the character), so keys pressed while locked would
        # otherwise look like an edit and unlock the saved state.
        if _is_disabled(getattr(event, "widget", None)):
            return
        entries[3].config(fg="black")
        # Invalidate save whenever any field is edited
        if saved["ok"]:
            saved["ok"] = False
            set_locked(False)
            result_label.config(text="Inputs changed — please Save again.", fg="red")

    def on_preset_change(*_):
        name = preset_var.get()
        if name == "none":
            # Selecting "none" resets every field back to its default.
            vals = dict(zip(FIELD_LABELS, DEFAULTS))
            vals.update(EXTRA_DEFAULTS)
            vals[CHANNEL_LABEL] = CHANNEL_DEFAULT
            for col in PASSFAIL_COLUMNS:
                vals[col] = PASSFAIL_DEFAULT
            num_data.set("0")
            avg_time.set("0")
        elif name in presets:
            vals = presets[name]
        else:
            return
        for entry, label in zip(entries, FIELD_LABELS):
            if isinstance(entry, tk.StringVar):
                entry.set(vals[label])
            else:
                entry.delete(0, tk.END)
                entry.insert(0, vals[label])
        for label in EXTRA_LABELS:
            extra_vars[label].set(vals[label])
        preset_channels = parse_channels(vals[CHANNEL_LABEL])
        for ch in CHANNEL_OPTIONS:
            channel_vars[ch].set(1 if ch in preset_channels else 0)
        for label, (mn, mx) in passfail_entries.items():
            for entry, bound in ((mn, "min"), (mx, "max")):
                entry.delete(0, tk.END)
                entry.insert(0, vals[passfail_col(label, bound)])
        on_entry_change()

    def on_run():
        if not saved["ok"]:
            return
        _last["fields"] = [e.get() for e in entries]
        _last["preset"] = preset_var.get()
        _last["extras"] = {label: extra_vars[label].get() for label in EXTRA_LABELS}
        _last["channels"] = channels_to_str(ch for ch in CHANNEL_OPTIONS if channel_vars[ch].get())
        _last["passfail"] = {label: (mn.get(), mx.get()) for label, (mn, mx) in passfail_entries.items()}

        ran["ok"] = True
        _state["has_run"] = True
        _state["pos"] = (root.winfo_x(), root.winfo_y())
        log.info("params: %s", params)
        # Tear down the power-readout window (and its refresh loop) first, so its
        # pending `after` callbacks don't fire after root.destroy() kills it.
        if _readout["close"]:
            _readout["close"]()
        _cancel_idle()
        result_label.config(text="Running...", fg="black")
        root.after(200, root.destroy)

    def on_read_power():
        if not saved["ok"] or not pm or not laser:
            return
        # Prevent opening multiple readout windows while one is already open.
        read_pm_btn.config(state="disabled")
        # Opens a separate window for the power readout.
        top = tk.Toplevel(root)
        top.title("Power Meter Readout")
        top.resizable(False, False)
        top.transient(root)
        # Check instruments
        check_inst(pm, laser)
        
        laser.write(f":SOURCE0:WAVE  {params.wl_stop:.3f} NM")
        laser.write(":SOURCE0:POWER:UNIT  0")
        laser.write(f":SOURCE0:POWER {params.tls_dbm} DBM")
        laser.write(":SOURCE0:POW:STATE 1")

        for i in range(1, 5):
            pm.write(f":SENSE{i}:POW:WAVE {params.wl_stop:.3f} NM")
            pm.write(f":SENSE{i}:POW:ATIME 25 MS")
            pm.write(f":INIT{i}:CONT 1")
            pm.write(f":SENSE{i}:POW:RANGE:AUTO 1")
        
        time.sleep(1)
        check_inst(pm, laser)

        # Show the wavelength / TLS power the readout is being taken at.
        info = tk.Frame(top)
        info.grid(row=0, column=0, columnspan=4, padx=10, pady=(10, 4), sticky="w")
        tk.Label(info, text="Wavelength (nm):", font=("TkDefaultFont", 10, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 6))
        tk.Label(info, text=f"{params.wl_stop}", font=("TkDefaultFont", 10)).grid(
            row=0, column=1, sticky="w", padx=(0, 20))
        tk.Label(info, text="TLS Power (dBm):", font=("TkDefaultFont", 10, "bold")).grid(
            row=1, column=0, sticky="w", padx=(0, 6))
        tk.Label(info, text=f"{params.tls_dbm}", font=("TkDefaultFont", 10)).grid(
            row=1, column=1, sticky="w")

        for col, text in enumerate(("Ch.", "Power Range (Auto)", "Power (dBm)", "Power (W)", "Max power (W)")):
            tk.Label(top, text=text, anchor="e", font=("TkDefaultFont", 10, "bold")).grid(
                row=1, column=col, padx=10, pady=(10, 4), sticky="e")

        range_vars, power_vars, watt_vars, max_vars = [], [], [], []
        # Track the peak power (in W) seen on each channel while the window is open.
        max_watts = [float("-inf")] * 4
        for i in range(4):
            rv, pv, wv, mv = (tk.StringVar(value="—"), tk.StringVar(value="—"),
                              tk.StringVar(value="—"), tk.StringVar(value="—"))
            tk.Label(top, text=str(i + 1), font=("TkDefaultFont", 14)).grid(
                row=i + 2, column=0, padx=10, pady=2)
            tk.Label(top, textvariable=rv, anchor="e", width=10,
                     font=("TkDefaultFont", 14)).grid(
                row=i + 2, column=1, padx=10, pady=2, sticky="e")
            tk.Label(top, textvariable=pv, anchor="e", width=12,
                     font=("TkDefaultFont", 14)).grid(
                row=i + 2, column=2, padx=10, pady=2, sticky="e")
            tk.Label(top, textvariable=wv, anchor="e", width=14,
                     font=("TkDefaultFont", 14)).grid(
                row=i + 2, column=3, padx=10, pady=2, sticky="e")
            tk.Label(top, textvariable=mv, anchor="e", width=14,
                     font=("TkDefaultFont", 14)).grid(
                row=i + 2, column=4, padx=10, pady=2, sticky="e")
            range_vars.append(rv)
            power_vars.append(pv)
            watt_vars.append(wv)
            max_vars.append(mv)

        job = {"id": None}

        def prettyprint(x, baseunit):
            prefix = "yzafpnµm kMGTPEZY"
            shift  = decimal.Decimal('1E24')
            d      = (decimal.Decimal(str(x))*shift).normalize()
            m, e   = d.to_eng_string().split('E')
            m = str(round(float(m), 3))
            return m + " " + prefix[int(e)//3] + baseunit

        def refresh():
            # Bail out if the window was torn down between the `after` being
            # scheduled and it firing.
            if not top.winfo_exists():
                return
            powers = pm.query(":FETCH:POW:ALL:CSV?").strip().split(',')
            p_ranges = [pm.query(f":SENSE{i}:POW:RANGE?") for i in range(1, 5)]
            for i in range(4):
                range_vars[i].set(f"{int(float(p_ranges[i]))} dBm")
                try:
                    p_w = float(powers[i])
                except (ValueError, IndexError):
                    watt_vars[i].set("-")
                    continue
 
                if p_w > 0.01:
                    watt_vars[i].set("overflown")
                    continue
 
                watt_vars[i].set(prettyprint(p_w, 'W'))
                if p_w > max_watts[i]:
                    max_watts[i] = p_w
                    max_vars[i].set(prettyprint(p_w, 'W'))
                # dBm = 10*log10(P / 1 mW); guard non-positive readings, which
                # the meter can report at/below its noise floor.
                if p_w > 0:
                    power_vars[i].set(f"{10 * math.log10(p_w * 1e3):.3f} dBm")
                else:
                    power_vars[i].set("—")
            job["id"] = top.after(50, refresh)

        def on_top_close():
            # Safety: turn off laser
            laser.write(":SOURCE0:POW:STATE 0")
            _readout["close"] = None
            if job["id"] is not None:
                try:
                    top.after_cancel(job["id"])
                except tk.TclError:
                    pass
                job["id"] = None
            if top.winfo_exists():
                top.destroy()
            if read_pm_btn.winfo_exists():
                read_pm_btn.config(state="normal")

        # Expose cleanup so root teardown (Run/Close) can cancel the refresh loop.
        _readout["close"] = on_top_close
        top.protocol("WM_DELETE_WINDOW", on_top_close)

        tk.Button(top, text="Close", command=on_top_close, width=10).grid(
            row=99, column=0, columnspan=5, pady=10)

        # Track the initial delayed refresh so it can be cancelled if the window
        # is closed within the first 1 seconds.
        job["id"] = top.after(1000, refresh)

    def on_save_preset():
        # Only reachable once parameters have passed Save's checks.
        if not saved["ok"]:
            return
        # Snapshot the current (validated) field values, keyed by CSV column.
        preset_vals = {label: entry.get() for entry, label in zip(entries, FIELD_LABELS)}
        for label in EXTRA_LABELS:
            preset_vals[label] = extra_vars[label].get()
        preset_vals[CHANNEL_LABEL] = channels_to_str(ch for ch in CHANNEL_OPTIONS if channel_vars[ch].get())
        for label, (mn, mx) in passfail_entries.items():
            preset_vals[passfail_col(label, "min")] = mn.get()
            preset_vals[passfail_col(label, "max")] = mx.get()

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
                presets.pop(name, None)   # keep the in-memory copy in sync with disk
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

            # Keep the in-memory copy in sync so it can be loaded without a rebuild.
            presets[name] = dict(preset_vals)

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
            # A set reference can always be unset.
            ref_btn.config(text="Unset Reference", state="normal")
        else:
            if _state["has_run"]:    
                status_value.config(text="Not Set / Available", fg="blue")
                ref_btn.config(text="Set Reference", state="normal")
            else:
                status_value.config(text="Not Set / Not Available", fg="blue")
                ref_btn.config(text="Set Reference", state="disabled")

    def on_toggle_ref():
        _state["reference"] = not _state["reference"]
        params.reference = _state["reference"]
        update_ref_ui()

    root = tk.Tk()
    root.title("Test Configuration")
    root.resizable(False, False)

    # Exceptions raised inside Tk callbacks (after/event/command handlers) don't
    # propagate out through mainloop(), so main.py's try/except never sees them.
    # Route them through our logger instead of Tk's default stderr-only print.
    def _log_tk_exception(exc, val, tb):
        log.error("Tkinter callback error", exc_info=(exc, val, tb))

    root.report_callback_exception = _log_tk_exception

    # Place the window at its fixed start position, or wherever the user last
    # left it. "+x+y" sets position only, leaving the auto-computed size alone.
    start_x, start_y = _state["pos"] or WINDOW_POS
    root.geometry(f"+{start_x}+{start_y}")

    def on_close():
        # Remember where the user left the window before closing.
        _state["pos"] = (root.winfo_x(), root.winfo_y())
        # Cancel the readout refresh loop before destroying its parent window.
        if _readout["close"]:
            _readout["close"]()
        _cancel_idle()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)

    frame = tk.Frame(root, padx=20, pady=15)
    frame.pack()

    N = len(FIELD_LABELS)

    # ---- Grid row layout -------------------------------------------------
    FIELDS_START = 2                     # preset at FIELDS_START, channel next, fields after
    CHANNEL_ROW  = FIELDS_START + 1      # channel checkboxes sit below Load Preset
    EXTRAS_START = FIELDS_START + N + 2   # rows for the three extra dropdowns
    LOGCOUNT_ROW = EXTRAS_START + 3
    AVGTIME_ROW  = LOGCOUNT_ROW + 1
    SAVEBTN_ROW  = AVGTIME_ROW + 1
    HEADER2_ROW  = SAVEBTN_ROW + 1
    RUNBTN_ROW   = HEADER2_ROW + 2   # +2 leaves room for the separator line
    HEADER3_ROW  = RUNBTN_ROW + 1
    REFBTN_ROW   = HEADER3_ROW + 2
    RESULT_ROW   = REFBTN_ROW + 1
    # Pass/Fail Conditions sit in their own sub-frame in column 2 (to the right
    # of the Parameters section), so they don't consume rows in columns 0–1.

    # ---- Set Parameters --------------------------------------------------
    section_header(frame, "Parameters", 0)

    presets = load_presets()
    preset_options = ["none"] + list(presets.keys())
    preset_var = tk.StringVar(value=_last.get("preset", "none"))
    tk.Label(frame, text="Load Preset", anchor="e").grid(row=FIELDS_START, column=0, pady=4, padx=(0, 8), sticky="e")
    preset_menu = tk.OptionMenu(frame, preset_var, *preset_options)
    preset_menu.grid(row=FIELDS_START, column=1, pady=4, sticky="w")
    preset_var.trace_add("write", on_preset_change)

    # Channel checkboxes (1–4). Default to channel 1; at least one is required.
    init_channels = parse_channels(_last.get("channels", CHANNEL_DEFAULT))
    channel_vars = {ch: tk.IntVar(value=1 if ch in init_channels else 0) for ch in CHANNEL_OPTIONS}
    tk.Label(frame, text=CHANNEL_LABEL, anchor="e").grid(row=CHANNEL_ROW, column=0, pady=4, padx=(0, 8), sticky="e")
    channel_frame = tk.Frame(frame)
    channel_frame.grid(row=CHANNEL_ROW, column=1, pady=4, sticky="w")
    channel_checks = []
    for ch in CHANNEL_OPTIONS:
        cb = tk.Checkbutton(channel_frame, text=str(ch), variable=channel_vars[ch], command=on_entry_change)
        cb.pack(side="left")
        channel_checks.append(cb)

    init_fields = _last.get("fields", DEFAULTS)
    entries = []
    entry_widgets = []
    for i, (label_text, default) in enumerate(zip(FIELD_LABELS, init_fields)):
        tk.Label(frame, text=label_text, anchor="e").grid(row=FIELDS_START+i+2, column=0, pady=4, padx=(0, 8), sticky="e")
        if i == 2:  # Sweep Speed — dropdown
            sv = tk.StringVar(value=default if default in SWEEP_SPEED_OPTIONS else SWEEP_SPEED_OPTIONS[0])
            menu = tk.OptionMenu(frame, sv, *SWEEP_SPEED_OPTIONS)
            menu.grid(row=FIELDS_START+i+2, column=1, pady=4, sticky="w")
            sv.trace_add("write", on_entry_change)
            entries.append(sv)
            entry_widgets.append(menu)
        else:
            e = tk.Entry(frame, width=20)
            e.insert(0, default)
            e.grid(row=FIELDS_START+i+2, column=1, pady=4, sticky="w")
            e.bind("<Key>", on_entry_change)
            entries.append(e)
            entry_widgets.append(e)

    # Platform's native disabled text color, restored when the step field isn't adjusted.
    default_disabledfg = entries[3].cget("disabledforeground")

    init_extras = _last.get("extras", EXTRA_DEFAULTS)
    extra_vars, extra_menus = make_extra_widgets(frame, EXTRAS_START, init_extras, on_entry_change)

    num_data = tk.StringVar(value="0")
    avg_time = tk.StringVar(value="0")

    tk.Label(frame, text="Log Count / Sweep", anchor="e").grid(row=LOGCOUNT_ROW, column=0, sticky="e", pady=4, padx=(0, 8))
    tk.Label(frame, textvariable=num_data, anchor="w").grid(row=LOGCOUNT_ROW, column=1, sticky="w", pady=4)

    tk.Label(frame, text="Averaging Time (μs)", anchor="e").grid(row=AVGTIME_ROW, column=0, sticky="e", pady=4, padx=(0, 8))
    tk.Label(frame, textvariable=avg_time, anchor="w").grid(row=AVGTIME_ROW, column=1, sticky="w", pady=4)

    # ---- Pass/Fail Conditions (right column) ----------------------------
    # A self-contained sub-frame placed to the right of the Parameters section.
    # Each criterion has a min and max float entry placed side by side; values
    # are validated and saved (and stored in presets) alongside the parameters.
    pf_container = tk.Frame(frame)
    pf_container.grid(row=0, column=2, rowspan=AVGTIME_ROW + 1, sticky="n", padx=(40, 0))
    section_header(pf_container, "Pass/Fail Conditions (Optional)", 0)
    init_passfail = _last.get("passfail", {})
    passfail_entries = {}   # label -> (min_entry, max_entry)
    passfail_widgets = []   # flat list for lock/unlock
    for j, label in enumerate(PASSFAIL_LABELS):
        tk.Label(pf_container, text=label, anchor="e").grid(row=j + 2, column=0, pady=4, padx=(0, 8), sticky="e")
        pf_frame = tk.Frame(pf_container)
        pf_frame.grid(row=j + 2, column=1, pady=4, sticky="w")
        lo_init, hi_init = init_passfail.get(label, (PASSFAIL_DEFAULT, PASSFAIL_DEFAULT))
        row_entries = []
        for bound_label, bound_init, pad in (("min", lo_init, (2, 12)), ("max", hi_init, (2, 0))):
            tk.Label(pf_frame, text=bound_label).pack(side="left")
            e = tk.Entry(pf_frame, width=8)
            e.insert(0, bound_init)
            e.pack(side="left", padx=pad)
            e.bind("<Key>", on_entry_change)
            row_entries.append(e)
            passfail_widgets.append(e)
        passfail_entries[label] = tuple(row_entries)

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
    inst_frame = tk.Frame(frame)
    inst_frame.grid(row=RUNBTN_ROW, column=0, columnspan=2, pady=10)
    run_btn = tk.Button(inst_frame, text="Run (Enter)", command=on_run, width=10, state="disabled")
    run_btn.pack(side="left", padx=5)
    read_pm_btn = tk.Button(inst_frame, text="Read Power...(p)", command=on_read_power, state="disabled")
    read_pm_btn.pack(side="left", padx=5)

    # ---- Reference -------------------------------------------------------
    # Status sits next to the section title instead of in its own field.
    ref_header = tk.Frame(frame)
    ref_header.grid(row=HEADER3_ROW, column=0, columnspan=2, sticky="w", pady=(10, 0))
    tk.Label(ref_header, text="Reference", font=("TkDefaultFont", 10, "bold")).pack(side="left")
    status_value = tk.Label(ref_header, text="Not Set", fg="blue", font=("TkDefaultFont", 10, "bold"))
    status_value.pack(side="left", padx=(8, 0))
    ttk.Separator(frame, orient="horizontal").grid(
        row=HEADER3_ROW + 1, column=0, columnspan=2, sticky="ew", pady=(0, 6))

    ref_frame = tk.Frame(frame)
    ref_frame.grid(row=REFBTN_ROW, column=0, columnspan=2, pady=4)
    ref_btn = tk.Button(ref_frame, text="Set Reference", command=on_toggle_ref, state="disabled")
    ref_btn.pack(side="left", padx=5)

    # Enter triggers Run when it's enabled (on_run is a no-op until saved).
    root.bind("<Return>", lambda _e: on_run())
    root.bind("<KP_Enter>", lambda _e: on_run())

    # 'p' triggers Read Power from anywhere in this window, like Enter does for
    # Run. Safe as a global shortcut because every field here is numeric, a
    # checkbox or a dropdown, so 'p' is never wanted as a literal character.
    # The one text field (new preset name) lives in a Toplevel, whose keys never
    # reach a binding made on root.
    def on_read_power_key(_e):
        if str(read_pm_btn["state"]) == "disabled":
            return
        on_read_power()
    root.bind("<KeyPress-p>", on_read_power_key)
    root.bind("<KeyPress-P>", on_read_power_key)

    result_label = tk.Label(frame, text="", wraplength=320, justify="left")
    result_label.grid(row=RESULT_ROW, column=0, columnspan=2)

    update_ref_ui()

    # Reopening with values from a previous run: auto-save so Run is ready
    # without pressing Save again. This also re-locks the parameter fields,
    # keeping the locked state across loops.
    if "fields" in _last:
        on_save()

    # Repeat from the plot window: the values are already saved (above), so just
    # fire Run once the window is up. Only valid when there are prior values to
    # re-run; a fresh session (no _last) can't auto-run.
    if auto_run and "fields" in _last:
        root.after(500, on_run)

    # ---- Idle timeout ----------------------------------------------------
    # Close after IDLE_SECONDS with no keyboard/button activity. On expiry reuse
    # on_close(), so get_inputs() returns None and main.py breaks the loop and
    # runs close_inst (laser off). Reset on key/button (mouse motion alone isn't
    # activity on a form); bind_all also covers the Read Power Toplevel.
    _idle_deadline = {"t": time.time() + IDLE_SECONDS}

    def _reset_idle(_e=None):
        _idle_deadline["t"] = time.time() + IDLE_SECONDS

    def _check_idle():
        _idle_job["id"] = None
        if not root.winfo_exists():
            return
        if time.time() >= _idle_deadline["t"]:
            log.info("Idle timeout — closing configuration window.")
            on_close()
            return
        _idle_job["id"] = root.after(IDLE_POLL_MS, _check_idle)

    root.bind_all("<Key>", _reset_idle, add="+")
    root.bind_all("<Button>", _reset_idle, add="+")
    _idle_job["id"] = root.after(IDLE_POLL_MS, _check_idle)

    # Grab keyboard focus so Enter works without clicking the window first
    # (on reopen, focus tends to stay on the console).
    root.lift()
    root.attributes("-topmost", True)
    root.after(0, lambda: root.attributes("-topmost", False))
    root.after(0, root.focus_force)

    root.mainloop()
    return params if ran["ok"] else None


if __name__ == "__main__":
    # pm, laser = prep_inst()
    
    while True:
        params = get_inputs()
        # params = get_inputs(pm, laser)
        if not params:
            break
        print(params)
