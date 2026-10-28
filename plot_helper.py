import math
import numpy as np
from constants import DELTA_LINE_MAX_POINTS
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


def delta_line(xs, ys, step, view=None, max_points=DELTA_LINE_MAX_POINTS):
    """Points along the line between the Delta markers (xs, ys, in click
    order), for the part of it inside `view`, an x-range (x0, x1), or for
    all of it when view is None.

    The points are generated, not downsampled: each segment gets one every
    k steps from its first marker, plus its last marker, so with the markers
    on data points they land on the data's wavelengths. k is the smallest
    whole number that keeps the visible line within max_points. One point
    past each edge of the view keeps the line running to the plot's border.
    Returns (x, y) arrays.
    """
    x0, x1 = sorted(view) if view else (-np.inf, np.inf)
    segments = list(zip(xs, ys, xs[1:], ys[1:]))
    seen = sum(max(0.0, min(max(xa, xb), x1) - max(min(xa, xb), x0))
               for xa, _, xb, _ in segments)
    gap = max(1, math.ceil(seen / (max_points * step))) * step
    lx, ly = [], []
    for xa, ya, xb, yb in segments:
        dx = xb - xa
        if dx == 0:   # a vertical step: just its two markers
            if x0 <= xa <= x1:
                lx.append([xa, xb])
                ly.append([ya, yb])
            continue
        sign, span = (1 if dx > 0 else -1), abs(dx)
        # The visible stretch, as distances from xa along the segment.
        lo, hi = sorted(((x0 - xa) * sign, (x1 - xa) * sign))
        lo, hi = max(lo, 0.0), min(hi, span)
        if lo > hi:
            continue
        n = int(span / gap + 1e-9)   # whole gaps in the segment
        last = math.ceil(hi / gap - 1e-9)
        j = np.arange(max(0, math.floor(lo / gap + 1e-9)), min(n, last) + 1)
        px = np.round(xa + sign * gap * j, 7)   # the wavelengths are rounded so too (gen_xaxis)
        lx.append(px)
        ly.append(ya + (px - xa) / dx * (yb - ya))
        if last > n and span - n * gap > 1e-9:   # the last marker, off the k-step grid
            lx.append([xb])
            ly.append([yb])
    if not lx:
        return np.array([]), np.array([])
    return np.concatenate(lx), np.concatenate(ly)

def gen_xaxis(params: Params, r):
    """Range r's wavelengths: one per logged point of the padded sweep, and
    the indices i_lo:i_hi that trim them to one step beyond λ start and λ stop."""
    start, stop, num_data = params.wl_start[r], params.wl_stop[r], params.num_data[r]
    wav_stop_tmp = start - params.padding + (params.step_pm * 1e-3) * (num_data - 1)
    wav_range    = np.linspace(start - params.padding, wav_stop_tmp, num_data).round(7)

    i_lo = np.searchsorted(wav_range, start - params.step_pm * 1e-3, side='left')
    i_hi = np.searchsorted(wav_range, stop  + params.step_pm * 1e-3, side='right')

    return wav_range, i_lo, i_hi

def pre_process(raw_w: Dataset, params: Params, r):
    """Range r's Dataset (in W) trimmed to its range, as (wavelengths, W, dBm)."""
    def wtodbm(x):
        """convert Watt to dBm

        Args:
            x (np.ndarray): 1-D numpy array in Watt

        Returns:
            np.ndarray: 1-D numpy array in dBm
        """
        return 10 * np.log10(x * 1000)
    
    wav_range, i_lo, i_hi = gen_xaxis(params, r)

    watt_s, dbm_s = Dataset(unit="W"), Dataset(unit="dBm")
    watt_s.scans = [[d[i_lo:i_hi] for d in scan] for scan in raw_w.scans]
    dbm_s.scans = [[wtodbm(d) for d in scan] for scan in watt_s.scans]
    watt_s.data = [d[i_lo:i_hi] for d in raw_w.data]
    dbm_s.data = [wtodbm(d) for d in watt_s.data]
    
    if params.reference and raw_w.ref:
        dbm_s.unit = "dB"
        watt_s.ref = [d[i_lo:i_hi] for d in raw_w.ref]
        watt_s.diff = [(d-r) for d, r in zip(watt_s.data, watt_s.ref)]
        dbm_s.ref = [wtodbm(d) for d in watt_s.ref]
        dbm_s.diff = [(d-r) for d, r in zip(dbm_s.data, dbm_s.ref)]
    
    return wav_range[i_lo:i_hi], watt_s, dbm_s