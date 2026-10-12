"""
analyze_data.py - Helper functions for data processing

Functions:
    combine_scans(scans)    Combine multiple scans for dynamic range scans
    peak_detection(data)    Find peaks and their bases and FWHMs
    find_bandwidth(wl, dbm, idx, y_offset, search_range)    Find the full width of the dip at idx, measured y_offset dB above its bottom, and whether both edges were found
"""
import numpy as np
from scipy.signal import find_peaks, peak_widths
import logging

from structs import Peak, Width, Params

log = logging.getLogger(__name__)

def combine_scans(scans):
    """Combines multiple scans. If scans has one scan, it just return the scan as a combined data.
    - Unit is Watt
    
       scans: list of list, [[Ch.1, ...] <- 1st scan, [Ch.1, ...]]
 
    Return:
        combined: [Ch.1, ...]
    """
    def combine(series):
        result = series[0].copy()
        for arr in series[1:]:
            mask = ~np.isnan(arr)
            result[mask] = arr[mask]
        return result

    return [combine(col) for col in zip(*scans)]    


def peak_detection(x: np.ndarray, tmp_y: np.ndarray, tune=None):
    # scipy's peak_widths requires float64 buffers; PM data is read as float32
    # y = np.asarray(data[1], dtype=np.float64)

    # increment on x-axis, assume the increment is constant between samples
    d_x = round(x[1] - x[0], 7) # nm
    
    # Find peaks
    # tunable parameters: prominence, distance, etc.
    # Absorption dips point down in dBm, but find_peaks/peak_widths only locate
    # maxima, so run them on a flipped copy (#90). Everything that comes back as
    # a y-value is negated again on the way out; depths/widths are unaffected.
    y = -tmp_y
    # Assume a peak should be deeper than 3/4 of global max-min
    simple_prominence = (np.max(y) - np.min(y)) * 0.5
    simple_distance = int(len(y)/4)
    peak_indices, peak_properties = find_peaks(y, width=1,rel_height=0.5, prominence=simple_prominence, distance=simple_distance)

    log.info(f"Peak(s) found: {len(peak_indices)}")
    if len(peak_indices) == 0:
        return None

    left_bases_is   = peak_properties['left_bases']
    right_bases_is  = peak_properties['right_bases']
    
    # left_ips, right_ips are fractional indices (interpolated positions)
    # Find peak depths - Max
    max_peak_depths = np.array([max(p-l, p-r) for p, l, r in zip(y[peak_indices], y[left_bases_is], y[right_bases_is])])
    
    max_widths, max_fwhm_dbm, max_l_ips, max_r_ips = peak_widths(y, peak_indices, rel_height=0.5, prominence_data=(max_peak_depths, left_bases_is, right_bases_is))
    
    # Find peak depths - Averaged
    avg_peak_depths = np.array([round(p-(l+r)/2, 7) for p, l, r in zip(y[peak_indices], y[left_bases_is], y[right_bases_is])])
    
    avg_widths, avg_fwhm_dbm, avg_l_ips, avg_r_ips = peak_widths(y, peak_indices, rel_height=0.5, prominence_data=(avg_peak_depths, left_bases_is, right_bases_is))

    return Peak(
        x_idx = peak_indices,
        x_nm  = x[peak_indices],
        l_idx = left_bases_is,
        r_idx = right_bases_is,
        max   = Width(
            l_nm  = np.array([x[int(ip)] + (ip % 1.0) * d_x for ip in max_l_ips]),
            r_nm  = np.array([x[int(ip)] + (ip % 1.0) * d_x for ip in max_r_ips]),
            w_pm  = np.array([(w * d_x) * 1000 for w in max_widths]),
            w_y   = -max_fwhm_dbm,
            depth = max_peak_depths,
        ),
        avg = Width(    
            l_nm  = np.array([x[int(ip)] + (ip % 1.0) * d_x for ip in avg_l_ips]),
            r_nm  = np.array([x[int(ip)] + (ip % 1.0) * d_x for ip in avg_r_ips]),
            w_pm  = np.array([(w * d_x) * 1000 for w in avg_widths]),
            w_y   = -avg_fwhm_dbm,
            depth = avg_peak_depths,
        ),
        min = Width(
            l_nm  = np.array([x[int(ip)] + (ip % 1.0) * d_x for ip in peak_properties['left_ips']]),
            r_nm  = np.array([x[int(ip)] + (ip % 1.0) * d_x for ip in peak_properties['right_ips']]),
            w_pm  = [(w * d_x) * 1000 for w in peak_properties['widths']],
            w_y   = -peak_properties['width_heights'],
            depth = peak_properties['prominences']
        ),
    )

def find_bandwidth(wl, tmp_dbm, idx, y_offset, search_range):
    """Full width of the dip at idx, measured y_offset dB above its bottom.

    Each side looks outward from idx, at most search_range samples, for the
    first sample at or above that level. Returns (left_nm, right_nm, width_pm,
    found). found is False when a side reached the end of its search without
    getting there: that edge then sits at the end of the search, so the width
    is cut short. Only x-positions are returned, so the flipped sign used
    below never reaches the caller.
    """
    # The search below is written for an upward peak; dips point down in dBm,
    # so work on a flipped copy (#90). Note this makes the local `dbm` the
    # opposite sign from the caller's — see the marker clamp in plot.py.
    dbm = -tmp_dbm
    height = float(dbm[idx]) - y_offset
    # The searches compare in float64, as float(dbm[i]) <= height does, even on
    # float32 data: a numpy float64 isn't narrowed to the array's type.
    level = np.float64(height)
    i_min = max(0, idx - search_range)
    # len(wl) - 1 (not len(wl)): the right side reads dbm[i] at i == i_max, so i_max must stay a valid index or it raises IndexError at the spectrum's end.
    i_max = min(len(wl) - 1, idx + search_range)

    # Left side: the nearest sample at or below height in (i_min, idx], else
    # i_min. Vectorized (rather than a sample-by-sample walk) so a wide search
    # stays fast; the result is the same.
    hits = np.flatnonzero(dbm[i_min + 1:idx + 1] <= level)
    i = i_min + 1 + int(hits[-1]) if hits.size else i_min
    left_found = float(dbm[i]) <= height
    left_ip = i
    if dbm[i] < height:
        if dbm[i + 1] != dbm[i]:
            left_ip += (height - dbm[i]) / (dbm[i + 1] - dbm[i])

    # Right side: the nearest sample at or below height in [idx, i_max), else i_max.
    hits = np.flatnonzero(dbm[idx:i_max] <= level)
    i = idx + int(hits[0]) if hits.size else i_max
    right_found = float(dbm[i]) <= height
    right_ip = i
    if dbm[i] < height:
        if dbm[i - 1] != dbm[i]:
            right_ip -= (height - dbm[i]) / (dbm[i - 1] - dbm[i])

    width_ip = right_ip - left_ip
    d_x      = round(wl[1] - wl[0], 7)

    left_nm  = wl[int(left_ip)]  + (left_ip  % 1.0) * d_x
    right_nm = wl[int(right_ip)] + (right_ip % 1.0) * d_x
    width_pm = width_ip * d_x * 1000

    return left_nm, right_nm, width_pm, left_found and right_found


def exam_peak(pk: Peak, params: Params):
    """Check one peak against the Pass/Fail criteria.

    The wavelength range picks the peak: of the peaks inside it (both ends
    included), the one with the largest Depth_max. That peak's Depth_max and
    FWHM_max are then checked against the depth and width ranges. A depth or
    width range left at 0 to 0 isn't checked.

    Returns a dict:
      verdict  'Pass', 'Fail', or None when every criterion is 0 (test off)
      peak     the tested peak's number (1-based), or None when none was picked
      note     why no peak was tested, or '' when one was
      checks   [wavelength, depth, width], each {'range': (lo, hi), or None
               when not set; 'value': the tested peak's value or None;
               'result': 'Pass', 'Fail', or None when not checked}
    """
    def in_between(x, crit):
        return crit[0] <= x <= crit[1]

    crit_loc = (params.wl_min, params.wl_max)
    crit_dep = (params.depth_min, params.depth_max)
    crit_wid = (params.width_min, params.width_max)

    # No criteria is given
    if sum(map(sum, [crit_loc, crit_dep, crit_wid])) == 0:
        return {'verdict': None, 'peak': None, 'note': '', 'checks': []}

    # The wavelength range always counts once the test is on; it's what
    # picks the peak, so without a peak in it the test fails.
    checks = [{'range': crit_loc, 'value': None, 'result': 'Fail'},
              {'range': crit_dep if sum(crit_dep) != 0 else None, 'value': None, 'result': None},
              {'range': crit_wid if sum(crit_wid) != 0 else None, 'value': None, 'result': None}]
    if pk is None:
        return {'verdict': 'Fail', 'peak': None, 'note': 'No peak detected', 'checks': checks}

    # If there are multiple peaks in the crit_loc range, the deepest is chosen
    # (the first of equally deep ones).
    inside = [i for i in range(len(pk.x_nm)) if in_between(pk.x_nm[i], crit_loc)]
    if not inside:
        return {'verdict': 'Fail', 'peak': None, 'note': 'No peak in the wavelength range',
                'checks': checks}
    i = max(inside, key=lambda j: pk.max.depth[j])

    for check, value in zip(checks, (pk.x_nm[i], pk.max.depth[i], pk.max.w_pm[i])):
        check['value'] = float(value)
        if check['range'] is not None:
            check['result'] = 'Pass' if in_between(value, check['range']) else 'Fail'
    verdict = 'Fail' if any(c['result'] == 'Fail' for c in checks) else 'Pass'
    return {'verdict': verdict, 'peak': i + 1, 'note': '', 'checks': checks}


if __name__ == "__main__":
    data = np.loadtxt("test_2026-05-11_14-44_converted.csv", skiprows=2, delimiter=',')
    print(peak_detection(data[:,0], data[:, 1]))