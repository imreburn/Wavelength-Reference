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

from structs import PeakInfo, Peaks, PeakFwhm, MaxPeak

log = logging.getLogger(__name__)

def combine_scans(scans):
    num_scans = len(scans)
    # Start with the first scan (with the highest range setting)
    wav_range = scans[0][1][0].copy()
    combined  = scans[0][1][1].copy()
    
    for i in range(1, num_scans):
        p_range, data = scans[i]
        p_range *= -1
        power = data[1]
        # log.info(f"Compare x-axis: {np.array_equal(wav_range, data[0])}")
        if i < num_scans - 1:
            next_p_range = scans[i+1][0] * -1
            combined = np.where((power >= p_range) & (power < next_p_range), power, combined)
        else:
            combined = np.where((power >= p_range), power, combined)
    return (wav_range, combined)


def peak_detection(data):
    x = data[0]
    y = data[1]
    # scipy's peak_widths requires float64 buffers; PM data is read as float32
    # y = np.asarray(data[1], dtype=np.float64)

    # increment on x-axis, assume the increment is constant between samples
    d_x = round(x[1] - x[0], 7) # nm
    
    # Find peaks
    # tunable parameters: prominence, distance, etc.
    # Assume a peak should be deeper than 3/4 of global max-min
    simple_prominence = (np.max(y) - np.min(y))*(3/4)
    
    peak_indices, peak_properties = find_peaks(y, prominence=simple_prominence, distance=8000)

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
    i_max = min(len(wl), idx + search_range)
    
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

if __name__ == "__main__":
    data = np.loadtxt("test_2026-05-11_14-44_converted.csv", skiprows=1, delimiter=',')
    print(peak_detection(data))