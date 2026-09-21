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
"""
import logging
import math
import threading

from config_helper import eng_format
from inst_helper import check_inst

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
# so a tick is one query, not eight.
RANGE_EVERY = 10

ATIME_MS    = 25
# Above this (or at/below zero) the meter is overloaded or dark: shown as "-".
MAX_VALID_W = 0.01

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
        self._lock    = threading.Lock()
        self._active  = False
        self._ranges  = None
        self._reads   = 0

    @property
    def has_laser(self):
        """False for an external source: the power field and On/Off are disabled."""
        return self.laser is not None

    # ---- lifecycle: one call per panel open / close ---------------------

    def start(self):
        """Meter into continuous auto-range mode, then re-apply the readout's
        own wavelength, power and emission state. After a sweep the laser is
        still where run_sweep left it, so this is what makes the fields true."""
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
        """One sample: [(range_dbm, watt), ...] for channels 1-4, updating max_w. watt is None when the reading is missing, dark or overloaded.

        wait=False returns None instead of blocking when another thread is mid-query (Dash ticks). Returns None when not active.
        """
        if not self._lock.acquire(blocking=wait):
            return None
        try:
            if not self._active:
                return None
            powers = self.pm.query(":FETCH:POW:ALL:CSV?").strip().split(',')
            if self._ranges is None or self._reads % RANGE_EVERY == 0:
                self._ranges = [float(self.pm.query(f":SENSE{i}:POW:RANGE?")) for i in range(1, 5)]
                self._read_actual()
            self._reads += 1
            rows = []
            for i in range(4):
                try:
                    w = float(powers[i])
                except (ValueError, IndexError):
                    w = None
                if w is not None and not (0 < w <= MAX_VALID_W):
                    w = None
                if w is not None and (self.max_w[i] is None or w > self.max_w[i]):
                    self.max_w[i] = w
                rows.append((self._ranges[i], w))
            return rows
        finally:
            self._lock.release()

    # ---- the controls behind the fields and buttons ---------------------

    def set_wavelength(self, text):
        """Apply a wavelength to the meter (all channels) and, if present, the laser. Returns an error message, or None when applied."""
        try:
            wl = float(text)
        except (TypeError, ValueError):
            return "Wavelength must be a number."
        lo, hi = self.spec["wl_min"], self.spec["wl_max"]
        if not (lo <= wl <= hi):
            return f"Wavelength must be between {lo:g} and {hi:g} nm."
        with self._lock:
            self._write_wavelength(wl)
        self.wl_nm = wl
        return None

    def set_power(self, text):
        """Apply a TLS power (dBm). Checked against the source's power rule for
        the current wavelength. Returns an error message, or None when applied.
        No-op without a laser."""
        if not self.laser:
            return None
        try:
            dbm = float(text)
        except (TypeError, ValueError):
            return "TLS power must be a number."
        rule = self._power_rule(self.wl_nm)
        if rule and dbm > rule[2]:
            lo, hi, lim = rule
            return f"TLS power exceeds the maximum ({lim:g} dBm) in {lo:g}-{hi:g} nm."
        with self._lock:
            self.laser.write(f":SOURCE0:POWER {dbm} DBM")
        self.dbm = dbm
        return None

    def set_emission(self, on):
        """Laser emission on/off. No-op without a laser."""
        if not self.laser:
            return
        with self._lock:
            self.laser.write(f":SOURCE0:POW:STATE {1 if on else 0}")
        self.emission = bool(on)

    def reset_max(self):
        with self._lock:
            self.max_w = [None] * 4

    # ---- internals (call with the lock held) ----------------------------

    def _read_actual(self):
        """Refresh `actual` from the instruments. Both report metres; the
        laser's power comes back in the unit start() selected (dBm)."""
        self.actual["pm_wl_nm"] = float(self.pm.query(":SENSE1:POW:WAV?")) * 1e9
        if self.laser:
            self.actual["laser_wl_nm"] = float(self.laser.query(":SOURCE0:WAV?")) * 1e9
            self.actual["laser_dbm"]   = float(self.laser.query(":SOURCE0:POW?"))

    def _write_wavelength(self, wl):
        for i in range(1, 5):
            self.pm.write(f":SENSE{i}:POW:WAVE {wl:.4f} NM")
        if self.laser:
            self.laser.write(f":SOURCE0:WAVE {wl:.4f} NM")

    def _power_rule(self, wl):
        """The (lo, hi, max_dbm) band that applies at `wl`: of the source's
        bands containing it, the one with the highest limit (same rule as
        validate_inputs). None when no band applies or the list is empty."""
        applicable = [rule for rule in self.spec["power_rules"] if rule[0] <= wl <= rule[1]]
        return max(applicable, key=lambda rule: rule[2]) if applicable else None


def format_actual(actual, has_laser):
    """Display strings (meter wavelength, laser wavelength, laser power) for
    the settings read-back, shared by both panels. None = not read yet;
    without a laser the two laser entries read "N/A"."""
    def wl(v):
        return "—" if v is None else f"{v:.4f}"
    pm_s = wl(actual["pm_wl_nm"])
    if not has_laser:
        return pm_s, "N/A", "N/A"
    dbm = actual["laser_dbm"]
    return pm_s, wl(actual["laser_wl_nm"]), "—" if dbm is None else f"{dbm:.3f}"


def format_row(range_dbm, watt, max_w):
    """Display strings (range, dBm, W, max W) for one channel, shared by both
    panels so they read the same. watt None = no valid reading this tick;
    max_w None = nothing valid seen since the last reset."""
    range_s = f"{int(range_dbm)} dBm"
    if watt is None:
        dbm_s = watt_s = "-"
    else:
        dbm_s  = f"{10 * math.log10(watt * 1e3):.3f} dBm"
        watt_s = eng_format(watt, "W")
    max_s = "—" if max_w is None else eng_format(max_w, "W")
    return range_s, dbm_s, watt_s, max_s
