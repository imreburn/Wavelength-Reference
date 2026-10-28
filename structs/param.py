from dataclasses import dataclass, field, fields
from typing import List, Tuple

Pair = Tuple[float, float]   # a peak test criterion's (min, max)


def _p(*, label=None, unit=None, group=None):
    """field() shorthand: default None, plus how Sweep Info should show it.

    All three are optional. A field declared without them still shows up in
    describe(), under group 'Other' with its attribute name as the label.
    """
    return field(default=None, metadata={'label': label, 'unit': unit, 'group': group})


def _fmt(value, unit=None):
    """Display text for one field value, with the unit appended if any. A
    list (one value per range) is comma-separated, and a pair in it, like a
    criterion's (min, max), is in brackets."""
    if isinstance(value, bool):                  # before int: bool is an int subclass
        text = 'Yes' if value else 'No'
    elif isinstance(value, (tuple, list)):
        text = ', '.join(f"[{', '.join(str(y) for y in x)}]" if isinstance(x, (tuple, list)) else str(x)
                         for x in value)
    else:
        text = str(value)                        # str(float) is exact; ':g' would truncate 1550.1234567
    return f'{text} {unit}' if unit else text


@dataclass
class Params:
    """One Run's settings. A sweep has one to four wavelength ranges: the
    fields that differ per range are lists, one value per range in range
    order, and the rest are shared by every range."""
    name      : str             = _p(label='Preset',              group='Sweep')

    wl_start  : List[float]     = _p(label='λ start',             unit='nm',   group='Sweep')
    wl_stop   : List[float]     = _p(label='λ stop',              unit='nm',   group='Sweep')
    padding   : float           = _p(label='λ padding',           unit='nm',   group='Sweep')
    speed     : float           = _p(label='Sweep speed',         unit='nm/s', group='Sweep')
    step_pm   : float           = _p(label='Step size',           unit='pm',   group='Sweep')
    tls_dbm   : float           = _p(label='TLS power',           unit='dBm',  group='Sweep')
    at_us     : float           = _p(label='Averaging time',      unit='µs', group='Sweep')
    num_data  : List[int]       = _p(label='Log count / sweep',   group='Sweep')
    pm_range  : int             = _p(label='Initial PM range',    unit='dBm',  group='Sweep')
    dyn_scans : int             = _p(label='Dynamic range scans', group='Sweep')
    decrement : int             = _p(label='Decrement',           unit='dB',   group='Sweep')
    reference : bool            = _p(label='Reference',           group='Sweep')
    channel   : Tuple[int, ...] = _p(label='Input channels',      group='Sweep')

    # The peak test, per range: each criterion's (min, max), and the base the
    # depth and width are measured from ("max", "avg" or "min").
    crit_wl   : List[Pair]      = _p(label='Peak λ',              unit='nm', group='Peak test criteria')
    crit_depth: List[Pair]      = _p(label='Peak depth',          unit='dB', group='Peak test criteria')
    crit_width: List[Pair]      = _p(label='Peak width',          unit='pm', group='Peak test criteria')
    crit_base : List[str]       = _p(label='Base',                group='Peak test criteria')

    label     : str             = _p(label='Label',               group='Run')
    save_raw  : bool            = _p(label='Auto-save raw data',  group='Run')
    source    : str             = _p(label='Source',              group='Run')
    detector  : str             = _p(label='Detector',            group='Run')
    time      : str             = _p(label='Time',                group='Run')
    date      : str             = _p(label='Date',                group='Run')
    version   : str             = _p(label='App version',         group='Run')

    def __post_init__(self):
        # JSON has no tuple type, so a saved-then-reloaded Params returns
        # channel and the criterion pairs as lists. Coerce to tuples so every
        # path is consistent.
        if self.channel is not None:
            self.channel = tuple(self.channel)
        for name in ('crit_wl', 'crit_depth', 'crit_width'):
            pairs = getattr(self, name)
            if pairs is not None:
                setattr(self, name, [tuple(p) for p in pairs])

    @property
    def n_ranges(self):
        """How many wavelength ranges the sweep has."""
        return len(self.wl_start)

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
