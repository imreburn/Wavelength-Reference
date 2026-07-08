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

from structs import PeakInfo, Peaks, PeakFwhm, MaxPeak, Params
from constants import POWER_LIMIT

log = logging.getLogger(__name__)

def combine_scans(scans, params: Params):
    """Combines multiple scans. If scans has one scan, it just return the scan as a combined data.
    - Unit is Watt
    
       scans: list of list, [[Ch.1, ...] <- 1st scan, [Ch.1, ...]]
 
    Return:
        combined: [Ch.1, ...]
    """
    # Start with the last scan (with the lowest power range setting)
    combined = scans[-1].copy()
    p_range = params.pm_range - (params.dyn_scans - 1) * params.decrement
    
    for scan in scans[-2::-1]:
        pow_limit_prev = POWER_LIMIT[str(p_range)]
        
        for ch_idx, ch_new in enumerate(scan):
            ch_com = combined[ch_idx]
            combined[ch_idx] = np.where((ch_new > pow_limit_prev), ch_new, ch_com)
            
        p_range += params.decrement

    return combined


def peak_detection(x, y):
    # scipy's peak_widths requires float64 buffers; PM data is read as float32
    # y = np.asarray(data[1], dtype=np.float64)

    # increment on x-axis, assume the increment is constant between samples
    d_x = round(x[1] - x[0], 7) # nm
    
    # Find peaks
    # tunable parameters: prominence, distance, etc.
    # Assume a peak should be deeper than 3/4 of global max-min
    simple_prominence = (np.max(y) - np.min(y)) * 0.5
    simple_distance = int(len(y)/4)
    peak_indices, peak_properties = find_peaks(y, prominence=simple_prominence, distance=simple_distance)

    log.info(f"Peak(s) found: {len(peak_indices)}")
    if len(peak_indices) == 0:
        return None

    # Prominence takes the shorter peak depth by definition
    min_peak_heights = peak_properties['prominences']
    left_bases_is    = peak_properties['left_bases']
    right_bases_is   = peak_properties['right_bases']
    
    # Find peak depths - Max
    max_peak_heights = np.array([max(p-l, p-r) for p, l, r in zip(y[peak_indices], y[left_bases_is], y[right_bases_is])])
    
    # Find peak depths - Averaged
    avg_peak_heights = np.array([round(p-(l+r)/2, 7) for p, l, r in zip(y[peak_indices], y[left_bases_is], y[right_bases_is])])

    # Find FWHM in two ways
    # left_ips, right_ips are fractional indices (interpolated positions)
    
    # Max
    max_widths, max_fwhm_dbm, max_l_ips, max_r_ips = peak_widths(y, peak_indices, rel_height=0.5, prominence_data=(max_peak_heights, left_bases_is, right_bases_is))
    
    # Averaged base
    avg_widths, avg_fwhm_dbm, avg_l_ips, avg_r_ips = peak_widths(y, peak_indices, rel_height=0.5, prominence_data=(avg_peak_heights, left_bases_is, right_bases_is))

    # Convert fractional indices in x-axis
    max_fwhm_left_nm  = [x[int(ip)] + (ip % 1.0) * d_x for ip in max_l_ips]
    max_fwhm_right_nm = [x[int(ip)] + (ip % 1.0) * d_x for ip in max_r_ips]
    max_fwhm_pm       = [(w * d_x) * 1000 for w in max_widths]
    
    avg_fwhm_left_nm  = [x[int(ip)] + (ip % 1.0) * d_x for ip in avg_l_ips]
    avg_fwhm_right_nm = [x[int(ip)] + (ip % 1.0) * d_x for ip in avg_r_ips]
    avg_fwhm_pm       = [(w * d_x) * 1000 for w in avg_widths]
    
    # Peak locations in nm
    peak_nm    = np.array(x[peak_indices])
    # Get the index of the highest peak
    max_peak_n = np.argmax(max_peak_heights)

    return PeakInfo(
        peaks=Peaks(
            idx        = peak_indices,
            wl         = peak_nm,
            lt_idx     = left_bases_is,
            rt_idx     = right_bases_is,
            max_depths = max_peak_heights,
            avg_depths = avg_peak_heights,
        ),
        max_fwhm=PeakFwhm(
            lt    = max_fwhm_left_nm,
            rt    = max_fwhm_right_nm,
            width = max_fwhm_pm,
            dbm   = max_fwhm_dbm,
        ),
        avg_fwhm=PeakFwhm(
            lt    = avg_fwhm_left_nm,
            rt    = avg_fwhm_right_nm,
            width = avg_fwhm_pm,
            dbm   = avg_fwhm_dbm,
        ),
        csv=MaxPeak(
            wl    = peak_nm[max_peak_n],
            depth = max_peak_heights[max_peak_n],
            fwhm  = max_fwhm_pm[max_peak_n],
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


def exam_peak(pk: PeakInfo, params: Params):
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
    for i in range(len(pk.peaks.wl)):
        if in_between(pk.peaks.wl[i], crit_loc):
            peak_found = True
            if pk.peaks.max_depths[i] > peak_dep:
                peak_idx = i
                peak_loc = pk.peaks.wl[i]
                peak_dep = pk.peaks.max_depths[i]
                peak_wid = pk.max_fwhm.width[i]
    
    if not peak_found:
        return "Fail", f"No peak found in {crit_loc}", None
    
    error_msg = []
    if not in_between(peak_dep, crit_dep) and sum(crit_dep) != 0:
        error_msg.append(f"Peak@{peak_loc:.3f}: depth({peak_dep:.5f}) not in {crit_dep}")
        
    if not in_between(peak_wid, crit_wid) and sum(crit_wid) != 0:
        error_msg.append(f"Peak@{peak_loc:.3f}: width({peak_wid:.3f}) not in {crit_wid}")
        
    if error_msg != []:
        return "Fail", ", ".join(error_msg), peak_idx
    
    return "Pass", f"Peak@{peak_loc:.3f} is in: location {crit_loc}, depth {crit_dep}, width {crit_wid}", peak_idx
        

if __name__ == "__main__":
    data = np.loadtxt("test_2026-05-11_14-44_converted.csv", skiprows=1, delimiter=',')
    print(peak_detection(data[:,0], data[:, 1]))