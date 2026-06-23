"""Smoothing filters for the spectrum plot's "Apply filter" modal.

Pure signal-processing logic, kept out of the Dash callback so display_plot()
stays readable as more filters are added. Every filter takes at most two
parameters, passed positionally as `parameter1` / `parameter2`. To add a filter:
  1. add an entry to FILTER_LABELS (value -> display name),
  2. add an entry to FILTER_PARAMS describing its 1-2 parameters
     (label + default); this drives the modal's two parameter inputs,
  3. add a branch in apply_filter() that reads parameter1/parameter2 and
     returns the filtered array (raise FilterError on bad input).
"""
import numpy as np
from scipy.signal import savgol_filter, get_window

# value -> display name. Drives the dropdown options and the legend name of
# the filtered trace.
FILTER_LABELS = {
    'rect'   : 'Rectangular',
    'tri'    : 'Triangular',
    'hann'   : 'Hann',
    'hamming': 'Hamming',
    'savgol' : 'Savitzky-Golay',
}

# value -> list of (label, default) for its parameters, in order. The modal
# shows one input per entry (max two): the first maps to `parameter1`, the
# second to `parameter2`. A single-entry list hides the second input.
FILTER_PARAMS = {
    'savgol' : [('Window size', 21), ('Polynomial degree', 3)],
    'rect'   : [('Window size', 21)],
    'tri'    : [('Window size', 21)],
    'hann'   : [('Window size', 21)],
    'hamming': [('Window size', 21)],
}

# Filters that smooth by convolving with a normalized window kernel; the
# value is the scipy.signal.get_window name. They all take a single
# parameter (the window size) as `parameter1`.
_WINDOW_KERNELS = {'rect': 'boxcar', 'tri': 'triang', 'hann': 'hann', 'hamming': 'hamming'}


class FilterError(ValueError):
    """Invalid filter parameters; the message is shown in the modal."""


def _to_int(value, name):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise FilterError(f"{name} must be an integer.")


def apply_filter(filt, signal, parameter1, parameter2):
    """Return `signal` filtered by `filt`.

    Parameters
    ----------
    filt : str
        A key from FILTER_LABELS.
    signal : 1-D array
        The data to smooth.
    parameter1, parameter2 : raw control values from the modal's two parameter
        inputs. Their meaning is per-filter (see FILTER_PARAMS); `parameter2`
        is unused by single-parameter filters.

    Raises
    ------
    FilterError
        On an unknown filter or invalid parameters.
    """
    n = len(signal)

    if filt == 'savgol':
        window = _to_int(parameter1, 'Window size')
        polyorder = _to_int(parameter2, 'Polynomial degree')
        if window < 1 or window > n:
            raise FilterError(f"Window size must be between 1 and {n}.")
        if window % 2 == 0:
            raise FilterError("Window size must be odd.")
        if polyorder < 0 or polyorder >= window:
            raise FilterError(
                "Polynomial degree must be >= 0 and less than the window size.")
        return savgol_filter(signal, window_length=window, polyorder=polyorder)

    if filt in _WINDOW_KERNELS:
        window = _to_int(parameter1, 'Window size')
        if window < 1 or window > n:
            raise FilterError(f"Window size must be between 1 and {n}.")
        # Convolve with a normalized window kernel. Edge-pad the signal
        # (replicate the end samples) so a 'valid' convolution keeps the
        # original length without the zero-padding roll-off at the ends.
        kernel = get_window(_WINDOW_KERNELS[filt], window, fftbins=False)
        kernel = kernel / kernel.sum()
        pad_lo, pad_hi = (window - 1) // 2, window // 2
        padded = np.pad(signal, (pad_lo, pad_hi), mode='edge')
        return np.convolve(padded, kernel, mode='valid')

    raise FilterError("Unknown filter.")
