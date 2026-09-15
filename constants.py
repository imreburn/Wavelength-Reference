"""
constants.py - Project-wide constants (pure data, no imports of project modules).

Keep this module a leaf in the dependency graph: it must not import hardware
libraries (e.g. pyvisa) or other project modules, so that analysis/plotting code
can import these values without any instrument backend present.
"""

# Application version (keep in sync with CHANGELOG.md)
APP_VERSION = "2.0.0"

# Instrument VISA addresses
VISA_ADDRESS_POWER_METER    = 'USB0::0x0957::0x3718::DE53500131::0::INSTR'
VISA_ADDRESS_TLS            = 'TCPIP0::100.65.2.45::inst0::INSTR'

# Laser sources offered at startup. "external": the app never talks to it —
# the user sets it up by hand and its trigger starts the power meter's log.
# "power_rules": (band_min, band_max, max_dbm). Of the bands that contain the
# whole sweep, the one with the highest limit applies; an empty list disables
# the check.
TLS_SOURCES = {
    "N7778C": {"wl_min": 1450, "wl_max": 1650, "external": False,
               "power_rules": [(1515, 1620, 11), (1480, 1630, 9), (1450, 1650, 5)]},
    "81600B": {"wl_min": 1259, "wl_max": 1378, "external": True,
               "power_rules": []},   # TODO: max output (dBm) from the 81600B datasheet
}

TLS_PASSWORD = 1234

# Power meter full-scale limit (Watt) per range setting (dBm, as string)
POWER_LIMIT = {"10" : 10e-3,
             "0"  : 1.9999e-3,
             "-10": 199.99e-6,
             "-20": 19.999e-6,
             "-30": 1.9999e-6,
             "-40": 199.99e-9,
             "-50": 19.999e-9,
             "-60": 1.9999e-9,
             "-70": 199.99e-12}

