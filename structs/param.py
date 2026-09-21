from dataclasses import dataclass, field, fields
from typing import Tuple


def _p(*, label=None, unit=None, group=None):
    """field() shorthand: default None, plus how Sweep Info should show it.

    All three are optional. A field declared without them still shows up in
    describe(), under group 'Other' with its attribute name as the label.
    """
    return field(default=None, metadata={'label': label, 'unit': unit, 'group': group})


def _fmt(value, unit=None):
    """Display text for one field value, with the unit appended if any."""
    if isinstance(value, bool):                  # before int: bool is an int subclass
        text = 'Yes' if value else 'No'
    elif isinstance(value, (tuple, list)):
        text = ', '.join(str(x) for x in value)
    else:
        text = str(value)                        # str(float) is exact; ':g' would truncate 1550.1234567
    return f'{text} {unit}' if unit else text


@dataclass
class Params:
    name      : str             = _p(label='Preset',              group='Sweep')

    wl_start  : float           = _p(label='Start wavelength',    unit='nm',   group='Sweep')
    wl_stop   : float           = _p(label='Stop wavelength',     unit='nm',   group='Sweep')
    padding   : float           = _p(label='Wavelength padding',  unit='nm',   group='Sweep')
    wl_st_pad : float           = _p(label='Padded start',        unit='nm',   group='Sweep')
    wl_sp_pad : float           = _p(label='Padded stop',         unit='nm',   group='Sweep')
    speed     : float           = _p(label='Sweep speed',         unit='nm/s', group='Sweep')
    step_pm   : float           = _p(label='Step size',           unit='pm',   group='Sweep')
    tls_dbm   : float           = _p(label='TLS power',           unit='dBm',  group='Sweep')
    at_us     : float           = _p(label='Averaging time',      unit='µs', group='Sweep')
    num_data  : int             = _p(label='Log count / sweep',   group='Sweep')
    pm_range  : int             = _p(label='Initial PM range',    unit='dBm',  group='Sweep')
    dyn_scans : int             = _p(label='Dynamic range scans', group='Sweep')
    decrement : int             = _p(label='Decrement',           unit='dB',   group='Sweep')
    reference : bool            = _p(label='Reference',           group='Sweep')
    channel   : Tuple[int, ...] = _p(label='Input channels',      group='Sweep')

    wl_min    : float           = _p(label='Peak wavelength min', unit='nm', group='Pass/fail criteria')
    wl_max    : float           = _p(label='Peak wavelength max', unit='nm', group='Pass/fail criteria')
    depth_min : float           = _p(label='Peak depth min',      unit='dB', group='Pass/fail criteria')
    depth_max : float           = _p(label='Peak depth max',      unit='dB', group='Pass/fail criteria')
    width_min : float           = _p(label='Peak width min',      unit='pm', group='Pass/fail criteria')
    width_max : float           = _p(label='Peak width max',      unit='pm', group='Pass/fail criteria')

    label     : str             = _p(label='Label',               group='Run')
    save_raw  : bool            = _p(label='Auto-save raw data',  group='Run')
    source    : str             = _p(label='Laser source',        group='Run')
    time      : str             = _p(label='Time',                group='Run')
    date      : str             = _p(label='Date',                group='Run')
    version   : str             = _p(label='App version',         group='Run')

    def __post_init__(self):
        # JSON has no tuple type, so a saved-then-reloaded Params returns
        # channel as a list. Coerce to tuple so every path is consistent.
        if self.channel is not None:
            self.channel = tuple(self.channel)

    def describe(self, *, skip_none=True):
        """Rows of (group, label, text) in declaration order, for display.

        Driven by fields(), so a field added later shows up on its own; label,
        unit and group come from the field metadata (see _p) with fallbacks.
        None values are skipped by default — e.g. a Params reloaded from an
        older CSV header simply lacks any newer field.
        """
        rows = []
        for f in fields(self):
            value = getattr(self, f.name)
            if value is None and skip_none:
                continue
            meta = f.metadata
            rows.append((meta.get('group') or 'Other',
                         meta.get('label') or f.name,
                         _fmt(value, meta.get('unit'))))
        return rows
