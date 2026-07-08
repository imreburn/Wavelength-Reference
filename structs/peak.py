from dataclasses import dataclass
import numpy as np

@dataclass
class PeakFwhm:
    lt   : list
    rt   : list
    width: list
    dbm  : list

@dataclass
class Peaks:
    idx       : np.ndarray
    wl        : np.ndarray
    lt_idx    : np.ndarray
    rt_idx    : np.ndarray
    max_depths: np.ndarray
    avg_depths: np.ndarray

@dataclass
class MaxPeak:
    wl   : float
    depth: float
    fwhm : float

@dataclass
class PeakInfo:
    peaks   : Peaks
    max_fwhm: PeakFwhm
    avg_fwhm: PeakFwhm
    csv     : MaxPeak
