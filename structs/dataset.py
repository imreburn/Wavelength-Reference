from dataclasses import dataclass, field
import numpy as np

@dataclass
class Dataset:
    unit : str
    data : list[np.ndarray]       = field(default_factory=list)
    diff : list[np.ndarray]       = field(default_factory=list)  
    ref  : list[np.ndarray]       = field(default_factory=list)
    scans: list[list[np.ndarray]] = field(default_factory=list)
    