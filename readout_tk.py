"""readout_tk.py - The live power readout as a Tk section of the config window.

Builds the widgets into a parent frame and runs the refresh tick on Tk's own
event loop. All instrument work is in readout.PowerReadout; this file only
formats what it returns and forwards the controls.
"""
import logging
import tkinter as tk

from config_helper import section_header
from readout import READOUT_COLUMNS, TK_REFRESH_MS, format_row, format_actual, format_wl

log = logging.getLogger(__name__)

VALUE_FONT  = ("TkDefaultFont", 12)
HEADER_FONT = ("TkDefaultFont", 10, "bold")
# Label widths (chars) for the four value columns: range, dBm, W, max W.
VALUE_WIDTHS = (7, 11, 11, 11)


class ReadoutSection:
    """Widgets plus tick. Pack or grid `.frame` where the section should sit,
    then start(); stop() before the window is torn down."""

    def __init__(self, parent, readout):
        self.readout  = readout
        self._job     = None      # pending after() id: the deferred start, or the next tick
        self._started = False

        f = self.frame = tk.Frame(parent)
        section_header(f, "Power Readout", 0)

        # ---- controls: Laser on, the wavelength and power fields with what
        # the instruments currently report to their right, then Apply and
        # Reset Max side by side
        ctrl = tk.Frame(f)
        ctrl.grid(row=2, column=0, columnspan=5, sticky="w", pady=(0, 2))
        self.laser_var = tk.IntVar(value=int(readout.emission))
        self.laser_cb  = tk.Checkbutton(ctrl, text="Laser on", variable=self.laser_var,
                                        command=self.toggle_laser)
        self.laser_cb.grid(row=0, column=0, columnspan=2, sticky="w")
        tk.Label(ctrl, text="Wavelength (nm)", anchor="e").grid(
            row=1, column=0, sticky="e", padx=(0, 6), pady=2)
        self.wl_entry = tk.Entry(ctrl, width=9)
        self.wl_entry.insert(0, format_wl(readout.wl_nm))
        self.wl_entry.grid(row=1, column=1, sticky="w", pady=2)
        self.wl_actual = tk.StringVar()
        tk.Label(ctrl, textvariable=self.wl_actual, fg="gray30").grid(
            row=1, column=2, sticky="w", padx=(10, 0))
        tk.Label(ctrl, text="TLS Power (dBm)", anchor="e").grid(
            row=2, column=0, sticky="e", padx=(0, 6), pady=2)
        self.dbm_entry = tk.Entry(ctrl, width=9)
        self.dbm_entry.insert(0, f"{readout.dbm:g}")
        self.dbm_entry.grid(row=2, column=1, sticky="w", pady=2)
        self.dbm_actual = tk.StringVar()
        tk.Label(ctrl, textvariable=self.dbm_actual, fg="gray30").grid(
            row=2, column=2, sticky="w", padx=(10, 0))
        self._show_actual()
        for e in (self.wl_entry, self.dbm_entry):
            e.bind("<Return>",   self._on_return)
            e.bind("<KP_Enter>", self._on_return)
        btns = tk.Frame(ctrl)
        btns.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        tk.Button(btns, text="Apply", command=self._on_apply_click, width=7).pack(side="left")
        tk.Button(btns, text="Reset Max", command=self.reset_max).pack(side="left", padx=(8, 0))
        if not readout.has_laser:
            # External source: the wavelength still goes to the meter (its
            # calibration), but there is no power or emission to set.
            self.dbm_entry.config(state="disabled")
            self.laser_cb.config(state="disabled")

        self.msg = tk.Label(f, text="", fg="red", wraplength=380, justify="left")
        self.msg.grid(row=3, column=0, columnspan=5, sticky="w")

        # ---- the table: header row, then one row per channel
        for col, text in enumerate(READOUT_COLUMNS):
            tk.Label(f, text=text, font=HEADER_FONT).grid(
                row=4, column=col, padx=3, pady=(4, 1), sticky="e")
        self.vars = []    # per channel: (range, dBm, W, max W) StringVars
        for i in range(4):
            tk.Label(f, text=str(i + 1), font=VALUE_FONT).grid(row=5 + i, column=0, padx=3)
            row_vars = tuple(tk.StringVar(value="—") for _ in VALUE_WIDTHS)
            for col, (var, width) in enumerate(zip(row_vars, VALUE_WIDTHS), start=1):
                tk.Label(f, textvariable=var, anchor="e", width=width, font=VALUE_FONT).grid(
                    row=5 + i, column=col, padx=3, sticky="e")
            self.vars.append(row_vars)

    # ---- lifecycle -------------------------------------------------------

    def start(self):
        """Start on the next event-loop pass, so the window paints before the
        instrument check (which sleeps) runs."""
        self._job = self.frame.after(0, self._begin)

    def _begin(self):
        self._job = None
        try:
            self.readout.start()
        except Exception:
            log.exception("Power readout failed to start")
            self.msg.config(text="Readout unavailable — see the log.")
            return
        self._started = True
        self._tick()

    def _tick(self):
        self._job = None
        if not self.frame.winfo_exists():
            return
        try:
            rows = self.readout.read()
        except Exception:
            # Don't keep hammering a failing instrument every 50 ms.
            log.exception("Power readout stopped: instrument error")
            self.msg.config(text="Readout stopped — instrument error, see the log.")
            return
        if rows is not None:
            for (rng, w), row_vars, max_w in zip(rows, self.vars, self.readout.max_w):
                for var, text in zip(row_vars, format_row(rng, w, max_w)):
                    var.set(text)
            self._show_actual()
        self._job = self.frame.after(TK_REFRESH_MS, self._tick)

    def stop(self):
        """Cancel the pending tick (or the deferred start) and release the
        readout. Call before the window is destroyed, so no `after` callback
        fires against dead widgets."""
        if self._job is not None:
            try:
                self.frame.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        if self._started:
            self._started = False
            self.readout.stop()

    def _show_actual(self):
        """The read-back labels: what the meter and laser report right now."""
        pm_s, lwl_s, ldbm_s = format_actual(self.readout.actual, self.readout.has_laser)
        self.wl_actual.set(f"PM {pm_s}, Laser {lwl_s}")
        self.dbm_actual.set(f"Laser {ldbm_s}")

    # ---- controls --------------------------------------------------------

    def apply(self):
        """Apply both fields. Returns True when they were accepted."""
        err = self.readout.set_wavelength(self.wl_entry.get())
        if err is None and self.readout.has_laser:
            err = self.readout.set_power(self.dbm_entry.get())
        self.msg.config(text=err or "Applied.", fg="red" if err else "blue")
        return err is None

    def _on_apply_click(self):
        # Clicking Apply also hands keyboard focus back to the window, so Enter
        # reaches root's Run binding again: the fields swallow Enter while they
        # have the focus, and nothing else in the window takes it on a click.
        # Enter inside a field applies but keeps the focus there, so a second
        # Enter can't start a sweep by accident. On an error the focus stays
        # put for the correction.
        if self.apply():
            self.frame.winfo_toplevel().focus_set()

    def _on_return(self, _event):
        self.apply()
        return "break"    # keep Enter in these fields from reaching root's Run binding

    def toggle_laser(self):
        self.readout.set_emission(bool(self.laser_var.get()))

    def reset_max(self):
        self.readout.reset_max()    # the next tick shows the cleared column
