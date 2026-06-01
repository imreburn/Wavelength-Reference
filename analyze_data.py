import numpy as np
from scipy.signal import find_peaks, peak_widths

from structs import PeakInfo, Peaks, PeakFwhm, MaxPeak

# Analyze peak(s)
def peak_detection(data):
    x = data[:, 0]
    y = data[:, 1]

    # increment on x-axis, assume the increment is constant between samples
    d_x = round(x[1] - x[0], 7) # nm
    
    # Find peaks
    # tunable parameters: prominence, distance
    # Assume a peak should be deeper than 3/4 of global max-min
    simple_prominence = (np.max(y) - np.min(y))*(3/4)
    peak_indices, peak_properties = find_peaks(y, prominence=simple_prominence, distance=8000)

    if len(peak_indices) == 0:
        print("No peak found")
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
    
    peak_nm    = np.array(x[peak_indices])
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

if __name__ == "__main__":
    data = np.loadtxt("test_2026-05-11_14-44_converted.csv", skiprows=1, delimiter=',')
    print(peak_detection(data))