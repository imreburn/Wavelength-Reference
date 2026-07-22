from dataclasses import dataclass
import numpy as np

@dataclass
class Width:
    l_nm : np.ndarray
    r_nm : np.ndarray
    w_pm : np.ndarray
    w_y  : np.ndarray
    depth: np.ndarray

@dataclass
class Peak:
    x_idx: np.ndarray
    x_nm : np.ndarray
    l_idx: np.ndarray
    r_idx: np.ndarray
    max  : Width
    avg  : Width
    min  : Width
        