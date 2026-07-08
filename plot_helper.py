import numpy as np
from structs import Dataset, Params

def lttb_multi(x, ys, n_out):
    """Largest-Triangle-Three-Buckets downsampling for several y-series.

    All series share one `x` axis. Each series is downsampled independently —
    the kept points differ because the triangle areas depend on the y-values —
    but the bucket layout and the next-bucket x-centroids depend only on `x` and
    `n_out`, so they are computed once and the per-bucket selection runs as a
    single loop vectorised across every series. This pays the (sequential)
    Python loop overhead once instead of once per trace.

    Parameters
    ----------
    x : 1-D array
        Shared x-axis (no spacing assumption — works for any monotonic x).
    ys : sequence of 1-D arrays
        One or more y-series, each the same length as `x`.
    n_out : int
        Target number of output points per series.

    Returns
    -------
    list of (x_sel, y_sel) tuples, one per input series.
    """
    x = np.asarray(x)
    ys = [np.asarray(y) for y in ys]
    n = len(x)
    if n <= n_out:
        return [(x, y) for y in ys]

    Y = np.vstack(ys)          # (T, n)
    T = Y.shape[0]

    buckets = np.array_split(np.arange(1, n - 1), n_out - 2)
    sel = np.empty((T, n_out), dtype=int)
    sel[:, 0] = 0
    sel[:, -1] = n - 1

    a = np.zeros(T, dtype=int)  # index of the last kept point, per series
    rows = np.arange(T)
    for i, bucket in enumerate(buckets):
        next_b = buckets[i + 1] if i + 1 < len(buckets) else np.array([n - 1])
        c_x = x[next_b].mean()            # scalar — same for every series
        c_y = Y[:, next_b].mean(axis=1)   # (T,)
        xa = x[a]                         # (T,)
        ya = Y[rows, a]                   # (T,)
        # Triangle areas for this bucket, per series: (T, bucket_size).
        areas = np.abs((xa - c_x)[:, None] * (Y[:, bucket] - ya[:, None]) -
                       (xa[:, None] - x[bucket][None, :]) * (c_y - ya)[:, None])
        a = bucket[np.argmax(areas, axis=1)]
        sel[:, i + 1] = a

    return [(x[sel[t]], Y[t][sel[t]]) for t in range(T)]


def lttb(x, y, n_out):
    """Single-series LTTB downsampling (thin wrapper over `lttb_multi`)."""
    return lttb_multi(x, [y], n_out)[0]

def gen_xaxis(params: Params):
    wav_stop_tmp = params.wl_start - params.padding + (params.step_pm * 1e-3) * (params.num_data - 1)
    wav_range    = np.linspace(params.wl_start - params.padding, wav_stop_tmp, params.num_data).round(7)

    i_lo = np.searchsorted(wav_range, params.wl_start - params.step_pm * 1e-3, side='left')
    i_hi = np.searchsorted(wav_range, params.wl_stop  + params.step_pm * 1e-3, side='right')
    
    return wav_range, i_lo, i_hi

def pre_process(raw_w: Dataset, params: Params):
    def wtodbm(x):
        """convert Watt to dBm, and multiply by -1 as it is loss

        Args:
            x (np.ndarray): 1-D numpy array in Watt

        Returns:
            np.ndarray: 1-D numpy array in dBm * (-1)
        """
        return -10 * np.log10(x * 1000)
    
    wav_range, i_lo, i_hi = gen_xaxis(params)
    
    watt_s, dbm_s = Dataset(unit="W"), Dataset(unit="dBm")
    watt_s.scans = [[d[i_lo:i_hi] for d in scan] for scan in raw_w.scans]
    dbm_s.scans = [[wtodbm(d) for d in scan] for scan in watt_s.scans]
    watt_s.data = [d[i_lo:i_hi] for d in raw_w.data]
    dbm_s.data = [wtodbm(d) for d in watt_s.data]
    
    if params.reference and raw_w.ref:
        dbm_s.unit = "dB"
        watt_s.ref = raw_w.ref[i_lo:i_hi]
        watt_s.diff = [(d-r) for d, r in zip(raw_w.data, raw_w.ref)]
        dbm_s.ref = [wtodbm(d) for d in watt_s.ref]
        dbm_s.diff = [(d-r) for d, r in zip(dbm_s.data, dbm_s.ref)]
    
    return wav_range[i_lo:i_hi], watt_s, dbm_s