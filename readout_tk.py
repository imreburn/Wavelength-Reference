"""readout_tk.py - The live power readout as a Tk section of the config window.

Builds the widgets into a parent frame and runs the refresh tick on Tk's own
event loop. All instrument work is in readout.PowerReadout; this file only
formats what it returns and forwards the controls. Its messages go to the
config window's Status section, through the callback it is given.
"""
import logging
import tkinter as tk
from tkinter import ttk

from config_helper import section_header, ui_font
from readout import READOUT_COLUMNS, TK_REFRESH_MS, format_row, format_actual, format_wl

log = logging.getLogger(__name__)

# Label widths (chars) for the four value columns: range, dBm, W, max W.
VALUE_WIDTHS = (7, 11, 11, 11)
# The text color of a row that shows nothing: an unchecked channel, or every
# channel while the readout is off. Its values read "—".
IDLE_FG = "gray60"
# The channel boxes' ttk style: their numbers in the table's value font.
CHANNEL_STYLE = "ReadoutChannel.TCheckbutton"

# The section's messages. They show in the config window's Status section,
# so each starts with where it comes from. The errors from the λ and power
# fields (readout.PowerReadout) follow MSG_PREFIX too.
MSG_PREFIX      = "Power Readout: "
MSG_UNAVAILABLE = MSG_PREFIX + "Unavailable. See the log."
MSG_STOPPED     = MSG_PREFIX + "Stopped by an instrument error. See the log."
MSG_APPLIED     = MSG_PREFIX + "Applied."
MSG_LASER_OFF_FAILED = MSG_PREFIX + "Couldn't turn the laser off. See the log."


class ReadoutSection:
    """Widgets plus tick. Pack or grid `.frame` where the section should sit,
    then start(); stop() before the window is torn down. `show_message(text,
    color)` shows the section's messages, in the config window's Status
    section."""

    def __init__(self, parent, readout, show_message):
        self.readout      = readout
        self.show_message = show_message
        self._job         = None      # pending after() id: the deferred start, or the next tick
        self._started     = False

        f = self.frame = ttk.Frame(parent)
        # The line spans the table plus an empty last column that takes any
        # width the parent stretches the frame to, so the line runs its full
        # width without moving the table.
        section_header(f, "Power Readout", 0, span=len(READOUT_COLUMNS) + 1)
        f.columnconfigure(len(READOUT_COLUMNS), weight=1)

        # ---- controls: Use Power Readout with Laser On under it; the
        # wavelength field, with "Use Range 1's (λ Start - λ Padding)" under
        # it; the power field; what the instruments currently report to the
        # right of each field; then Apply and Reset Max side by side
        ctrl = ttk.Frame(f)
        ctrl.grid(row=2, column=0, columnspan=5, sticky="w", pady=(0, 2))
        toggles = ttk.Frame(ctrl)
        toggles.grid(row=0, column=0, columnspan=3, sticky="w")
        # The config window binds the P key to this box and L to the next.
        # A 4 px gap between the two (the user's pick, 2026-11-18).
        self.enable_var = tk.IntVar(value=int(readout.enabled))
        self.enable_cb  = ttk.Checkbutton(toggles, text="Use Power Readout (P)",
                                          variable=self.enable_var, command=self.toggle_enabled)
        self.enable_cb.pack(anchor="w")
        self.laser_var = tk.IntVar(value=int(readout.emission))
        self.laser_cb  = ttk.Checkbutton(toggles, text="Laser On (L)", variable=self.laser_var,
                                         command=self.toggle_laser)
        self.laser_cb.pack(anchor="w", pady=(4, 0))
        ttk.Label(ctrl, text="λ (nm)", anchor="e").grid(
            row=1, column=0, sticky="e", padx=(0, 6), pady=2)
        self.wl_entry = ttk.Entry(ctrl, width=9)
        self.wl_entry.insert(0, format_wl(readout.wl_nm))
        self.wl_entry.grid(row=1, column=1, sticky="w", pady=2)
        self.wl_actual = tk.StringVar()
        ttk.Label(ctrl, textvariable=self.wl_actual, foreground="gray30").grid(
            row=1, column=2, sticky="w", padx=(10, 0))
        # Under the λ field, reaching under the read-back so its long text
        # doesn't widen the field's column.
        self.follow_var = tk.IntVar(value=int(readout.follow_start))
        self.follow_cb  = ttk.Checkbutton(ctrl, text="Use Range 1's (λ Start - λ Padding)",
                                          variable=self.follow_var, command=self.toggle_follow)
        self.follow_cb.grid(row=2, column=1, columnspan=2, sticky="w")
        ttk.Label(ctrl, text="TLS Power (dBm)", anchor="e").grid(
            row=3, column=0, sticky="e", padx=(0, 6), pady=2)
        self.dbm_entry = ttk.Entry(ctrl, width=9)
        self.dbm_entry.insert(0, f"{readout.dbm:g}")
        self.dbm_entry.grid(row=3, column=1, sticky="w", pady=2)
        self.dbm_actual = tk.StringVar()
        ttk.Label(ctrl, textvariable=self.dbm_actual, foreground="gray30").grid(
            row=3, column=2, sticky="w", padx=(10, 0))
        btns = ttk.Frame(ctrl)
        btns.grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.apply_btn = ttk.Button(btns, text="Apply", command=self._on_apply_click, width=7)
        self.apply_btn.pack(side="left")
        self.reset_btn = ttk.Button(btns, text="Reset Max", command=self.reset_max)
        self.reset_btn.pack(side="left", padx=(8, 0))

        # ---- the table: header row, then one row per channel, its checkbox
        # in the Ch. column. It sits right under the buttons, as close as the
        # fields above them sit to each other: the messages are in the Status
        # section.
        value_font, header_font = ui_font(11), ui_font(10, "bold")
        ttk.Style(f).configure(CHANNEL_STYLE, font=value_font)
        for col, text in enumerate(READOUT_COLUMNS):
            ttk.Label(f, text=text, font=header_font).grid(
                row=3, column=col, padx=3, pady=(4, 1), sticky="w" if col == 0 else "e")
        self.ch_vars  = []    # per channel: its checkbox's IntVar
        self.ch_cbs   = []
        self.rows     = []    # per channel: ((StringVar, Label), ...) for range, dBm, W, max W
        self._row_fg  = [None] * 4
        for i in range(4):
            var = tk.IntVar(value=int(i + 1 in readout.channels))
            cb = ttk.Checkbutton(f, text=str(i + 1), variable=var, style=CHANNEL_STYLE,
                                 command=self.channels_changed)
            cb.grid(row=4 + i, column=0, padx=(0, 3), sticky="w")
            self.ch_vars.append(var)
            self.ch_cbs.append(cb)
            cells = []
            for col, width in enumerate(VALUE_WIDTHS, start=1):
                var_ = tk.StringVar(value="—")
                label = ttk.Label(f, textvariable=var_, anchor="e", width=width, font=value_font)
                label.grid(row=4 + i, column=col, padx=3, sticky="e")
                cells.append((var_, label))
            self.rows.append(tuple(cells))
        # A live row's color: "" leaves it to the ttk theme.
        self._value_fg = ""

        self._set_states()
        self._show_rows(None)
        self._show_actual()

    # ---- lifecycle -------------------------------------------------------

    def start(self):
        """Start on the next event-loop pass, so the window paints before the
        instrument check (which sleeps) runs. Does nothing while Use Power
        Readout is off, or once started."""
        if not self.readout.enabled or self._started or self._job is not None:
            return
        self._job = self.frame.after(0, self._begin)

    def _begin(self):
        self._job = None
        try:
            self.readout.start()
        except Exception:
            log.exception("Power readout failed to start")
            self.show_message(MSG_UNAVAILABLE, "red")
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
            self.show_message(MSG_STOPPED, "red")
            return
        if rows is not None:
            self._show_rows(rows)
            self._show_actual()
            # Follow the laser if its front-panel button changed emission.
            # set() does not fire the Checkbutton's command, so this sends
            # nothing back to the laser.
            self.laser_var.set(int(self.readout.emission))
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

    # ---- what the section shows ------------------------------------------

    def _set_states(self):
        """Enable the controls to match the settings. While the readout is off,
        only Use Power Readout stays enabled. The λ field is disabled while it
        follows the sweep's start, which needs saved Parameters: while they're
        unlocked it stays editable, box or not. An external source has no
        power or Laser On."""
        on = self.readout.enabled
        state = "normal" if on else "disabled"
        laser_state = state if self.readout.has_laser else "disabled"
        self.laser_cb.config(state=laser_state)
        self.dbm_entry.config(state=laser_state)
        self.wl_entry.config(state="disabled" if self.readout.following else state)
        for w in (self.follow_cb, self.apply_btn, self.reset_btn, *self.ch_cbs):
            w.config(state=state)

    def _set_wl_field(self, text):
        """Write the λ field, even while it's disabled."""
        state = str(self.wl_entry.cget("state"))
        self.wl_entry.config(state="normal")
        self.wl_entry.delete(0, tk.END)
        self.wl_entry.insert(0, text)
        self.wl_entry.config(state=state)

    def _show_rows(self, rows):
        """Fill the table from read()'s rows. None (not read yet, or the
        readout is off) leaves dashes. A row with nothing to show (unchecked,
        or the readout off) is gray."""
        for i, cells in enumerate(self.rows):
            row = rows[i] if rows is not None else None
            if row is None:
                texts = ("—",) * len(VALUE_WIDTHS)
                live = rows is None and self.readout.enabled and i + 1 in self.readout.channels
            else:
                texts = format_row(*row, self.readout.max_w[i])
                live = True
            for (var, _), text in zip(cells, texts):
                var.set(text)
            fg = self._value_fg if live else IDLE_FG
            if fg != self._row_fg[i]:
                self._row_fg[i] = fg
                for _, label in cells:
                    label.config(foreground=fg)

    def _show_actual(self):
        """The read-back labels: what the meter and laser report right now,
        or dashes while the readout is off."""
        actual = self.readout.actual if self.readout.enabled else dict.fromkeys(self.readout.actual)
        pm_s, lwl_s, ldbm_s = format_actual(actual, self.readout.has_laser)
        self.wl_actual.set(f"PM {pm_s}, Laser {lwl_s}")
        self.dbm_actual.set(f"Laser {ldbm_s}")

    # ---- controls --------------------------------------------------------

    def toggle_enabled(self):
        """Use Power Readout, with Laser On following it (readout.set_enabled).
        On checks Laser On and runs the readout's start() (the instrument
        check, then its setup, which turns the laser on); off stops the tick
        and turns the laser off, the only command it sends."""
        on = bool(self.enable_var.get())
        if not on:
            self.stop()
        try:
            self.readout.set_enabled(on)
        except Exception:
            log.exception("Power readout: the laser didn't turn off")
            self.show_message(MSG_LASER_OFF_FAILED, "red")
        self.laser_var.set(int(self.readout.emission))
        self._set_states()
        self._show_rows(None)
        self._show_actual()
        if on:
            self.start()

    def toggle_follow(self):
        """Use Range 1's (λ Start - λ Padding). Checking it moves the readout to
        the saved Parameters' sweep start; while they're unlocked it changes
        nothing yet, and the λ field keeps what was typed. Unchecking leaves
        the λ field to edit, and sends nothing."""
        self.readout.follow_start = bool(self.follow_var.get())
        if self.readout.following:
            error = self.readout.follow()
            if error:
                self.show_message(MSG_PREFIX + error, "red")
            self._set_wl_field(format_wl(self.readout.wl_nm))
        self._set_states()

    def sweep_saved(self, params):
        """Save's hook: Range 1's λ Start or the padding may have changed. With
        the box checked, the λ field follows from now on, grayed. Returns the
        message to show, or None."""
        error = self.readout.set_sweep_start(params)
        if self.readout.following:
            self._set_wl_field(format_wl(self.readout.wl_nm))
        self._set_states()
        return None if error is None else MSG_PREFIX + error

    def params_unlocked(self):
        """The config window's hook for unlocked Parameters (a new window,
        Change, or an edit): the λ field opens for editing until the next
        Save, even with the box checked. Sends nothing."""
        self.readout.params_unlocked()
        self._set_states()

    def channels_changed(self):
        self.readout.set_channels(i + 1 for i, var in enumerate(self.ch_vars) if var.get())
        if not self._started:
            self._show_rows(None)     # no tick to show it
        else:
            self._show_actual()

    def apply(self):
        """Apply both fields. Returns True when they were accepted."""
        if not self.readout.enabled:
            return False
        err = self.readout.apply(self.wl_entry.get(), self.dbm_entry.get())
        if err:
            self.show_message(MSG_PREFIX + err, "red")
        else:
            self.show_message(MSG_APPLIED, "blue")
        return err is None

    def _on_apply_click(self):
        # Only a click applies the fields: Enter in them does nothing (#141).
        # A click gives Apply the keyboard focus, so after a successful Apply
        # it goes to the window instead, where Space can't apply again. On an
        # error it stays on Apply.
        if self.apply():
            self.frame.winfo_toplevel().focus_set()

    def toggle_laser(self):
        self.readout.set_emission(bool(self.laser_var.get()))

    def reset_max(self):
        self.readout.reset_max()    # the next tick shows the cleared column
