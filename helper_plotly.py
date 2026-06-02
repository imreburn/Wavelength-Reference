import numpy as np

def lttb(x, y, n_out):
    """Largest-Triangle-Three-Buckets downsampling (pure numpy, no deps)."""
    n = len(x)
    if n <= n_out:
        return x, y
    buckets = np.array_split(np.arange(1, n - 1), n_out - 2)
    out = [0]
    for i, bucket in enumerate(buckets):
        next_b = buckets[i + 1] if i + 1 < len(buckets) else np.array([n - 1])
        a = out[-1]
        c_x = x[next_b].mean()
        c_y = y[next_b].mean()
        areas = np.abs((x[a] - c_x) * (y[bucket] - y[a]) -
                        (x[a] - x[bucket]) * (c_y - y[a]))
        out.append(bucket[np.argmax(areas)])
    out.append(n - 1)
    idx = np.array(out)
    return x[idx], y[idx]