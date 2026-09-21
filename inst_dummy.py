"""inst_dummy.py - Stand-ins for the power meter and the TLS, for running the
UI on a machine without instruments (the Mac). They answer just the SCPI
subset that check_inst and readout.PowerReadout use; anything else is accepted
and ignored. The meter goes dark when the dummy laser is off and scales with
its power, so the readout's controls visibly do something.
"""
import math
import random
import time

from constants import POWER_LIMIT, TLS_SOURCES
from readout import PowerReadout, DEFAULT_DBM


class DummyLaser:
    def __init__(self):
        self.wl_nm = None
        self.dbm   = DEFAULT_DBM
        self.on    = False

    def write(self, cmd):
        parts = cmd.upper().split()
        if len(parts) < 2:
            return
        head, arg = parts[0], parts[1]
        if head == ":SOURCE0:POW:STATE":
            self.on = arg == "1"
        elif head == ":SOURCE0:POWER":
            self.dbm = float(arg)
        elif head == ":SOURCE0:WAVE":
            self.wl_nm = float(arg)

    def query(self, cmd):
        c = cmd.upper()
        if c.startswith(":SYST:ERR:COUN"):
            return "0"
        if c.startswith(":LOCK"):
            return "0"
        if c.startswith("*OPC"):
            return "1"
        if c.startswith("*IDN"):
            return "Dummy TLS"
        if c.startswith(":SOURCE0:POW:STATE"):
            return "1" if self.on else "0"
        if c.startswith(":SOURCE0:POW?"):
            return f"{self.dbm:.6e}"
        if c.startswith(":SOURCE0:WAV?"):
            return f"{(self.wl_nm or 0.0) * 1e-9:.6e}"     # metres, like the 816x
        return "0"

    def clear(self):
        pass

    def close(self):
        pass


class DummyPM:
    # Power per channel (W) at DEFAULT_DBM: two live channels, one dark (shows
    # "-") and one near the top of the -10 dBm range.
    BASE_W = (57e-6, 4.1e-6, -2e-12, 180e-6)

    def __init__(self, laser=None):
        self.laser = laser        # None: external source, always lit
        self.wl_nm = None
        self._t0   = time.time()

    def _powers(self):
        if self.laser is not None and not self.laser.on:
            return [-1e-12 * random.random() for _ in range(4)]   # dark: shows as "-"
        gain = 10 ** ((self.laser.dbm - DEFAULT_DBM) / 10) if self.laser else 1.0
        t = time.time() - self._t0
        out = []
        for i, base in enumerate(self.BASE_W):
            drift = 1 + 0.03 * math.sin(t / 3 + i)      # slow wander so the numbers move
            noise = 1 + random.gauss(0, 0.004)
            out.append(base * gain * drift * noise)
        return out

    @staticmethod
    def _auto_range(w):
        """The range the meter would pick: the smallest whose full scale covers w."""
        for dbm, limit in sorted(POWER_LIMIT.items(), key=lambda kv: kv[1]):
            if abs(w) <= limit:
                return dbm
        return "10"

    def write(self, cmd):
        parts = cmd.upper().split()
        if len(parts) >= 2 and parts[0].endswith(":POW:WAVE"):
            self.wl_nm = float(parts[1])

    def query(self, cmd):
        c = cmd.upper()
        if c.startswith(":FETCH:POW:ALL:CSV"):
            return ",".join(f"{w:.6e}" for w in self._powers())
        if ":POW:RANGE?" in c:
            ch = int(c[len(":SENSE")])
            return self._auto_range(self._powers()[ch - 1])
        if c.endswith(":POW:WAV?"):
            return f"{(self.wl_nm or 0.0) * 1e-9:.6e}"     # metres, like the 8163
        if c.startswith(":SYST:ERR"):
            return '0,"No error"'
        if c.startswith("*OPC"):
            return "1"
        if c.startswith("*IDN"):
            return "Dummy PM"
        return "0"

    def clear(self):
        pass

    def close(self):
        pass


def dummy_readout(source):
    """A PowerReadout on dummy instruments for the given TLS_SOURCES key.
    External sources get no laser, as in the real app."""
    spec  = TLS_SOURCES[source]
    laser = None if spec["external"] else DummyLaser()
    return PowerReadout(DummyPM(laser), laser, spec)
