from dataclasses import dataclass, field

@dataclass
class Params:
    wl_start   : float = field(default=None)
    wl_stop    : float = field(default=None)
    speed      : float = field(default=None)
    step_pm    : float = field(default=None)
    tls_dbm    : float = field(default=None)
    num_data   : int   = field(default=None)
    at_us      : float = field(default=None)
    padding    : float = field(default=None)
    csv        : str   = field(default=None)
    csv_fname  : str   = field(default=None)
    peak_csv   : str   = field(default=None)
    peak_fname: str    = field(default=None)
    peak_label: str    = field(default=None)
    time       : str   = field(default=None)
    date       : str   = field(default=None)