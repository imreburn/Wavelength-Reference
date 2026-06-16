import numpy as np


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
