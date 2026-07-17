from dataclasses import dataclass, field
from typing import Tuple

@dataclass
class Params:
    name      : str             = field(default=None)
    
    wl_start  : float           = field(default=None)
    wl_stop   : float           = field(default=None)
    padding   : float           = field(default=None)
    speed     : float           = field(default=None)
    step_pm   : float           = field(default=None)
    tls_dbm   : float           = field(default=None)
    at_us     : float           = field(default=None)
    num_data  : int             = field(default=None)
    pm_range  : int             = field(default=None)
    dyn_scans : int             = field(default=None)
    decrement : int             = field(default=None)
    reference : bool            = field(default=None)
    channel   : Tuple[int, ...] = field(default=None)
    
    wl_min    : float           = field(default=None)
    wl_max    : float           = field(default=None)
    depth_min : float           = field(default=None)
    depth_max : float           = field(default=None)
    width_min : float           = field(default=None)
    width_max : float           = field(default=None)
    
    time      : str             = field(default=None)
    date      : str             = field(default=None)
    version   : str             = field(default=None)
    
    def __post_init__(self):
        # JSON has no tuple type, so a saved-then-reloaded Params returns
        # channel as a list. Coerce to tuple so every path is consistent.
        if self.channel is not None:
            self.channel = tuple(self.channel)