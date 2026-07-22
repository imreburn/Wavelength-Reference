"""
analyze_data.py - Helper functions for data processing

Functions:
    combine_scans(scans)    Combine multiple scans for dynamic range scans
    peak_detection(data)    Find peaks and their bases and FWHMs
    find_bandwidth(wl, dbm, idx, y_offset, search_range)    Find a full width an offset by bandwidth amplitude (y-offset) above given x-position
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


def peak_detection(x: np.ndarray, y: np.ndarray, tune=None):
    # scipy's peak_widths requires float64 buffers; PM data is read as float32
    # y = np.asarray(data[1], dtype=np.float64)

    # increment on x-axis, assume the increment is constant between samples
    d_x = round(x[1] - x[0], 7) # nm
    
    # Find peaks
    # tunable parameters: prominence, distance, etc.
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
            w_y   = max_fwhm_dbm,
            depth = max_peak_depths,
        ),
        avg = Width(    
            l_nm  = np.array([x[int(ip)] + (ip % 1.0) * d_x for ip in avg_l_ips]),
            r_nm  = np.array([x[int(ip)] + (ip % 1.0) * d_x for ip in avg_r_ips]),
            w_pm  = np.array([(w * d_x) * 1000 for w in avg_widths]),
            w_y   = avg_fwhm_dbm,
            depth = avg_peak_depths,
        ),
        min = Width(
            l_nm  = np.array([x[int(ip)] + (ip % 1.0) * d_x for ip in peak_properties['left_ips']]),
            r_nm  = np.array([x[int(ip)] + (ip % 1.0) * d_x for ip in peak_properties['right_ips']]),
            w_pm  = [(w * d_x) * 1000 for w in peak_properties['widths']],
            w_y   = peak_properties['width_heights'],
            depth = peak_properties['prominences']
        ),
    )

def find_bandwidth(wl, dbm, idx, y_offset, search_range):
    height = float(dbm[idx]) - y_offset
    i_min = max(0, idx - search_range)
    # len(wl) - 1 (not len(wl)): the right-side loop below reads dbm[i] at i == i_max,
    # so i_max must stay a valid index or it raises IndexError at the spectrum's end.
    i_max = min(len(wl) - 1, idx + search_range)
    
    # left side
    i = idx
    while i_min < i and height < float(dbm[i]):
        i -= 1
    left_ip = i
    if dbm[i] < height:
        if dbm[i + 1] != dbm[i]:
            left_ip += (height - dbm[i]) / (dbm[i + 1] - dbm[i])
            
    # right side
    i = idx
    while i < i_max and height < float(dbm[i]):
        i += 1
    right_ip = i
    if dbm[i] < height:
        if dbm[i - 1] != dbm[i]:
            right_ip -= (height - dbm[i]) / (dbm[i - 1] - dbm[i])
    
    width_ip = right_ip - left_ip
    d_x      = round(wl[1] - wl[0], 7)
    
    left_nm  = wl[int(left_ip)]  + (left_ip  % 1.0) * d_x
    right_nm = wl[int(right_ip)] + (right_ip % 1.0) * d_x
    width_pm = width_ip * d_x * 1000
    
    return left_nm, right_nm, width_pm


def exam_peak(pk: Peak, params: Params):
    def in_between(x, crit):
        return x >= crit[0] and x <= crit[1]
    
    crit_loc = (params.wl_min, params.wl_max)
    crit_dep = (params.depth_min, params.depth_max)
    crit_wid = (params.width_min, params.width_max)
        
    # No criteria is given
    if sum(map(sum, [crit_loc, crit_dep, crit_wid])) == 0:
        return None, None, None
    
    if pk is None:
        return "Fail", "No peak detected", None
    
    peak_idx, peak_loc, peak_dep, peak_wid = 0, 0, 0, 0
    peak_found = False
    # If there are multiple peaks in the crit_loc range,
    # the peak with the the deepest depth will be chosen.
    for i in range(len(pk.x_nm)):
        if in_between(pk.x_nm[i], crit_loc):
            peak_found = True
            if pk.max.depth[i] > peak_dep:
                peak_idx = i + 1
                peak_loc = pk.x_nm[i]
                peak_dep = pk.max.depth[i]
                peak_wid = pk.max.w_pm[i]
    
    if not peak_found:
        return "Fail", f"No peak found in {crit_loc}", None
    
    error_msg = []
    peak_msg = f'P{peak_idx}@{peak_loc:.3f}:'
    if not in_between(peak_dep, crit_dep) and sum(crit_dep) != 0:
        error_msg.append(f" depth ({peak_dep:.3f}) outside {crit_dep}")
        
    if not in_between(peak_wid, crit_wid) and sum(crit_wid) != 0:
        error_msg.append(f" width ({peak_wid:.3f}) outside {crit_wid}")
        
    if error_msg != []:
        return "Fail", peak_msg + ",".join(error_msg), peak_idx
    
    return "Pass", peak_msg+f" within wavelength {crit_loc}"+(f", depth {crit_dep}" if sum(crit_dep) > 0 else "") + (f", width {crit_wid}" if sum(crit_wid) > 0 else ""), peak_idx
        

if __name__ == "__main__":
    data = np.loadtxt("test_2026-05-11_14-44_converted.csv", skiprows=2, delimiter=',')
    print(peak_detection(data[:,0], data[:, 1]))