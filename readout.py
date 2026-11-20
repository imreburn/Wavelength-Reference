"""readout.py - Instrument side of the live power readout. No Tk, no Dash.

One PowerReadout per session: main.py builds it right after prep_inst and
hands it to both windows. It owns every meter/laser command the readout
needs, the running max per channel and a lock, so the two panels that show
it - the section in the config window (readout_tk.py) and the modal in the
plot (plot.py) - only build widgets, run a timer and format what read()
returns.

Lifecycle per panel: start() when it appears, read() on every tick, stop()
when it goes away. The sweep never overlaps a read: the config window stops
the readout before Run tears the window down, and the plot stops it when its
modal closes and again after the pywebview window has gone.

Three session settings live here too, so both panels show the same thing:
`enabled` ("Use Power Readout", off when the app starts: while it's off the
panels never call start() or read(), and Laser On follows it, see
set_enabled()), `channels` (the channels shown and queried) and
`follow_start` ("Use Range 1's (λ Start - λ Padding)": while the readout
is on, the wavelength follows the sweep's first wavelength in the saved
Parameters, which the panels pass in; see follow()).
"""
import logging
import math
import threading

from config_helper import eng_format
from inst_helper import check_inst
from inst_run import padded_range

log = logging.getLogger(__name__)

# Field defaults on first use.
# DEFAULT_WL_NM = 1500.0
DEFAULT_DBM   = 0.1

# Refresh period per host. Tk runs the tick on its own event loop with nothing
# else contending for the meter. Dash pays an HTTP round trip per tick and its
# callbacks run on a worker pool, so it polls more slowly.
TK_REFRESH_MS   = 50
DASH_REFRESH_MS = 100

# Ranges and the settings read-back change rarely; refetch them every Nth read
# so a tick is one query, not nine.
RANGE_EVERY = 10

ATIME_MS    = 25
# Readings outside [DARK_FLOOR_W, MAX_VALID_W] show as a fixed label instead
# of a number. The N7748A's dark noise stays under 0.1 pW (either sign), so a
# dark channel stays below the floor instead of flickering between a number
# and a label each time the noise crosses zero.
DARK_FLOOR_W = 1e-13    # -100 dBm
MAX_VALID_W  = 0.01     # +10 dBm, full scale of the top range
DARK_LABELS  = ("< -100 dBm", "< 0.1 pW")    # (dBm, W) columns
OVER_LABELS  = ("> +10 dBm", "> 10 mW")

READOUT_COLUMNS = ("Ch.", "Range (Auto)", "Power (dBm)", "Power (W)", "Max power (W)")


class PowerReadout:
    """Meter/laser commands, running max, settings read-back and lock behind
    the live readout."""

    def __init__(self, pm, laser, source_spec):
        self.pm    = pm
        self.laser = laser            # None for an external source
        self.spec  = source_spec      # the TLS_SOURCES entry: limits for the fields
        self.wl_nm    = int((source_spec["wl_min"] + source_spec["wl_max"])/2)
        self.dbm      = DEFAULT_DBM
        self.emission = False   # laser off by default
        self.max_w    = [None] * 4    # carries over between windows until reset_max()
        # What the instruments report for the wavelength (meter, laser) and the
        # TLS power, in nm / dBm. Refreshed with the ranges every RANGE_EVERY
        # reads rather than once after Apply: "Applied." only means the command
        # went out, and a laser keeps tuning for a moment after :WAVE. None
        # until the first read; the laser entries stay None without a laser.
        self.actual   = {"pm_wl_nm": None, "laser_wl_nm": None, "laser_dbm": None}
        self.enabled  = False         # "Use Power Readout": off when the app starts
        self.channels = {1}           # the channels shown and queried, out of 1-4
        self.follow_start = True      # "Use Range 1's (λ Start - λ Padding)"
        # The TLS power cap: the lowest of the source's power limits. A power
        # at or below it is allowed at every wavelength, so the wavelength can
        # move without a power check. None for a source without power rules.
        limits = [rule[2] for rule in source_spec["power_rules"]]
        self.max_dbm  = min(limits) if limits else None
        self._lock    = threading.Lock()
        self._active  = False
        self._ranges  = None
        self._reads   = 0

    @property
    def has_laser(self):
        """False for an external source: the power field and On/Off are disabled."""
        return self.laser is not None

    def following(self, params):
        """True while the wavelength follows Range 1's λ Start - λ Padding: the
        box is checked and there are saved Parameters. `params` is what the
        panel has saved: None before the first Save and while the config
        window's Parameters are unlocked (the graph window's always are). The
        panels gray the λ field only then, so it stays editable while the
        Parameters are unlocked."""
        return self.follow_start and params is not None

    # ---- lifecycle: one call per panel open / close ---------------------

    def start(self):
        """Meter into continuous auto-range mode, then re-apply the readout's
        own wavelength, power and emission state. After a sweep the laser is
        still where run_sweep left it, so this is what makes the fields true.
        Sets up all four channels, checked or not: it runs once per panel
        open, not on every read, and a channel checked later is then ready."""
        with self._lock:
            check_inst(self.pm, self.laser)
            if self.laser:
                self.laser.write(":SOURCE0:POWER:UNIT 0")
                self.laser.write(f":SOURCE0:POWER {self.dbm} DBM")
                self.laser.write(f":SOURCE0:POW:STATE {int(self.emission)}")
            self._write_wavelength(self.wl_nm)
            for i in range(1, 5):
                self.pm.write(f":SENSE{i}:POW:ATIME {ATIME_MS} MS")
                self.pm.write(f":INIT{i}:CONT 1")
                self.pm.write(f":SENSE{i}:POW:RANGE:AUTO 1")
            self._ranges = None
            self._reads  = 0
            self._active = True
        log.info("[READOUT] started: %.3f nm, %s dBm, laser %s",
                 self.wl_nm, self.dbm, "on" if self.emission else "off")

    def stop(self):
        """Mark inactive. Takes the lock, so a read in progress on another
        thread has finished by the time this returns and the meter can go to
        the sweep at once. Nothing is undone on the meter (arm_pm resets it)
        and the laser stays as the user left it. Safe to call twice."""
        with self._lock:
            self._active = False

    # ---- one sample; the caller owns the timer --------------------------

    def read(self, wait=True):
        """One sample: one entry per channel 1-4, (range_dbm, watt) for a checked channel and None for an unchecked one, updating max_w. watt is None when the reading is missing or not a finite number. Dark or overloaded readings come back as they are, for format_row to label, and don't count toward max_w.

        One :FETCH:POW:ALL:CSV? per read returns all four channels; only the checked ones are used. The per-channel queries every RANGE_EVERY reads go to the checked channels only. With no channel checked the meter isn't queried at all, and only the laser's read-back runs.

        wait=False returns None instead of blocking when another thread is mid-query (Dash ticks). Returns None when not active.
        """
        if not self._lock.acquire(blocking=wait):
            return None
        try:
            if not self._active:
                return None
            channels = sorted(self.channels)
            powers = self.pm.query(":FETCH:POW:ALL:CSV?").strip().split(',') if channels else []
            if self._ranges is None or self._reads % RANGE_EVERY == 0:
                ranges = {i: float(self.pm.query(f":SENSE{i}:POW:RANGE?")) for i in channels}
                self._ranges = [ranges.get(i) for i in range(1, 5)]
                self._read_actual()
            self._reads += 1
            rows = []
            for i in range(4):
                if i + 1 not in channels:
                    rows.append(None)
                    continue
                try:
                    w = float(powers[i])
                except (ValueError, IndexError):
                    w = None
                if w is not None and not math.isfinite(w):
                    w = None
                if (w is not None and DARK_FLOOR_W <= w <= MAX_VALID_W
                        and (self.max_w[i] is None or w > self.max_w[i])):
                    self.max_w[i] = w
                rows.append((self._ranges[i], w))
            return rows
        finally:
            self._lock.release()

    # ---- the controls behind the fields and buttons ---------------------

    def set_enabled(self, on):
        """Use Power Readout. Laser On follows it, and can still be changed by
        hand afterward. On: Laser On is checked, so the panel's start() turns
        the laser on with the rest of its setup. Off: the readings stop and the
        laser goes off (:SOURCE0:POW:STATE 0), the only command this sends.
        The readout is off even if that command fails; the error is raised for
        the panel to report. Without a laser, only the setting changes."""
        if on:
            self.enabled = True
            if self.laser:
                self.emission = True
            return
        try:
            with self._lock:
                self._active = False
                if self.laser:
                    self.laser.write(":SOURCE0:POW:STATE 0")
                    self.emission = False
        finally:
            self.enabled = False
        log.info("[READOUT] turned off%s", ", laser off" if self.laser else "")

    def apply(self, wl_text, dbm_text):
        """Apply: check both fields first, the TLS power against the cap
        (max_dbm), and only then send them, in this order: the wavelength to
        the meter (all channels) and the laser, then the power. Returns an
        error message, and then nothing was sent, or None when applied.
        Without a laser only the wavelength goes out. Refused while the
        readout is off (the panels disable Apply then)."""
        if not self.enabled:
            return "Use Power Readout is off."
        wl, error = self._parse_wavelength(wl_text)
        if error:
            return error
        dbm = None
        if self.laser:
            try:
                dbm = float(dbm_text)
            except (TypeError, ValueError):
                return "TLS power must be a number."
            if not math.isfinite(dbm):
                return "TLS power must be a number."
            if self.max_dbm is not None and dbm > self.max_dbm:
                return f"TLS power must be {self.max_dbm:g} dBm or less."
        with self._lock:
            self._write_wavelength(wl)
            if self.laser:
                self.laser.write(f":SOURCE0:POWER {dbm} DBM")
        self.wl_nm = wl
        if self.laser:
            self.dbm = dbm
        return None

    def set_channels(self, channels):
        """The channels to show and query. Sends nothing: start() set up all
        four, so a newly checked channel is ready. One that's newly checked
        starts a fresh max, and the next read fetches its range at once."""
        channels = {int(c) for c in channels} & {1, 2, 3, 4}
        with self._lock:
            added = channels - self.channels
            for i in added:
                self.max_w[i - 1] = None
            if added:
                self._ranges = None
            if not channels:
                self.actual["pm_wl_nm"] = None
            self.channels = channels

    def follow(self, params):
        """"Use Range 1's (λ Start - λ Padding)": move the readout's wavelength
        to Range 1's start in the saved Parameters `params` (see following()),
        where the sweep sends the laser first (inst_run.padded_range), clamped
        to the source's range. The panels call it when the readout turns on,
        when the box gets checked, and on a Save while the readout is on. Does
        nothing while the readout is off, the box is unchecked or there are no
        saved Parameters. Sends Apply's wavelength commands, only when the
        wavelength changes and the readout is running; otherwise only the
        setting changes, and the next start() sends it. No power check: the
        TLS power is at most max_dbm, which every wavelength allows."""
        if not (self.enabled and self.following(params)):
            return
        lo, hi = self.spec["wl_min"], self.spec["wl_max"]
        wl = min(max(padded_range(params, 0)[0], lo), hi)
        if wl == self.wl_nm:
            return
        with self._lock:
            if self._active:
                self._write_wavelength(wl)
            self.wl_nm = wl

    def set_emission(self, on):
        """Laser emission on/off. No-op without a laser, or while the readout
        is off (the panels disable Laser On then)."""
        if not self.laser or not self.enabled:
            return
        with self._lock:
            self.laser.write(f":SOURCE0:POW:STATE {1 if on else 0}")
            # Inside the lock, so _read_actual never sees the new state with
            # the old flag and logs it as a front-panel change.
            self.emission = bool(on)

    def reset_max(self):
        with self._lock:
            self.max_w = [None] * 4

    # ---- internals (call with the lock held) ----------------------------

    def _read_actual(self):
        """Refresh `actual` from the instruments. Both report metres; the
        laser's power comes back in the unit start() selected (dBm). Also
        syncs `emission` with the laser, since its front-panel button can
        switch emission without going through set_emission(). The meter's
        wavelength comes from the lowest checked channel: every channel gets
        the same wavelength, so it speaks for the others."""
        channels = sorted(self.channels)
        self.actual["pm_wl_nm"] = (float(self.pm.query(f":SENSE{channels[0]}:POW:WAV?")) * 1e9
                                   if channels else None)
        if self.laser:
            self.actual["laser_wl_nm"] = float(self.laser.query(":SOURCE0:WAV?")) * 1e9
            self.actual["laser_dbm"]   = float(self.laser.query(":SOURCE0:POW?"))
            on = bool(int(self.laser.query(":SOURCE0:POW:STATE?")))
            if on != self.emission:
                log.info("[READOUT] laser turned %s at the instrument", "on" if on else "off")
                self.emission = on

    def _write_wavelength(self, wl):
        for i in range(1, 5):
            self.pm.write(f":SENSE{i}:POW:WAVE {wl:.3f} NM")
        if self.laser:
            self.laser.write(f":SOURCE0:WAVE {wl:.5f} NM")

    def _parse_wavelength(self, text):
        """(wavelength, None), or (None, error message) for a field that isn't
        a number inside the source's range."""
        try:
            wl = float(text)
        except (TypeError, ValueError):
            return None, "Wavelength must be a number."
        lo, hi = self.spec["wl_min"], self.spec["wl_max"]
        if not (lo <= wl <= hi):
            return None, f"Wavelength must be between {lo:g} and {hi:g} nm."
        return wl, None


def format_wl(wl_nm):
    """The wavelength setting for the input field, shared by both panels: up to
    the 5 decimals the laser takes (see _write_wavelength), trailing zeros
    dropped. Not `:g`, which keeps 6 significant digits (1550.123 -> 1550.12)."""
    return f"{wl_nm:.3f}".rstrip("0").rstrip(".")


def format_actual(actual, has_laser):
    """Display strings (meter wavelength, laser wavelength, laser power) for
    the settings read-back, shared by both panels. None = not read yet;
    without a laser the two laser entries read "N/A"."""
    def wl(v):
        return "—" if v is None else f"{v:.3f}"
    pm_s = wl(actual["pm_wl_nm"])
    if not has_laser:
        return pm_s, "N/A", "N/A"
    dbm = actual["laser_dbm"]
    return pm_s, wl(actual["laser_wl_nm"]), "—" if dbm is None else f"{dbm:.3f}"


def format_row(range_dbm, watt, max_w):
    """Display strings (range, dBm, W, max W) for one channel, shared by both
    panels so they read the same. watt None = no reading this tick; below
    DARK_FLOOR_W or above MAX_VALID_W it shows as dark or overloaded.
    max_w None = nothing valid seen since the last reset."""
    range_s = f"{int(range_dbm)} dBm"
    if watt is None:
        dbm_s = watt_s = "-"
    elif watt < DARK_FLOOR_W:
        dbm_s, watt_s = DARK_LABELS
    elif watt > MAX_VALID_W:
        dbm_s, watt_s = OVER_LABELS
    else:
        dbm_s  = f"{10 * math.log10(watt * 1e3):.3f} dBm"
        watt_s = eng_format(watt, "W")
    max_s = "—" if max_w is None else eng_format(max_w, "W")
    return range_s, dbm_s, watt_s, max_s
