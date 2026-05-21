import os
import numpy as np
import pandas as pd
from scipy.signal import find_peaks, peak_widths

# Analyze peak(s)
def peak_detection(df, params=None):
    x = df["Wavelength"]
    y = df["Power"]

    if params != None:
        peak_csv    = params["peak_csv"]
        file_name   = params["peak_file_name"]
        label       = params["peak_label"]
    else:   # For plot_csv.py
        peak_csv    = "n"
        file_name   = ".csv"
        label       = "none"

    # increment on x-axis, assume the increment is constant between samples
    d_x         = x.iloc[1] - x.iloc[0] # in nm
    
    # Find peaks
    # tunable parameters: prominence, distance
    # Assume a peak should be deeper than 3/4 of global max-min
    simple_prominence = (y.max() - y.min())*(3/4)
    peak_indices, peak_properties = find_peaks(y, prominence=simple_prominence, distance=8000)

    peak_prominences    = peak_properties['prominences']
    # These are actual indices
    left_bases          = peak_properties['left_bases']
    right_bases         = peak_properties['right_bases']
    
    # Find peak depths - MinMax
    peak_depths = [max(p-l, p-r) for p, l, r in zip(y.iloc[peak_indices], y.iloc[left_bases], y.iloc[right_bases])]

    # Find FWHM
    # FIXME: can we use this function?
    # left_ips, right_ips are fractional indices
    widths, width_heights, left_ips, right_ips = peak_widths(y, peak_indices, rel_height=0.5, prominence_data=(peak_prominences, left_bases, right_bases))

    # Convert fractional indices in x-axis
    left_hm_xs  = [x.iloc[int(ip)] + (ip % 1.0) * d_x for ip in left_ips]
    right_hm_xs = [x.iloc[int(ip)] + (ip % 1.0) * d_x for ip in right_ips]
    widths_x = [(w * d_x)*1000 for w in widths]

    # Get max peak
    max_peak_index  = np.argmax(peak_prominences)
    max_peak_x      = x.iloc[peak_indices[max_peak_index]]
    max_peak_depth  = max(peak_depths)
    max_peak_fwhm   = (widths_x[max_peak_index])   # in picometer

    peak_info = {
        "peak_indices": peak_indices,
        "peak_depths": peak_depths,
        "left_bases": left_bases,
        "right_bases": right_bases,
        "fwhm_heights": width_heights,
        "fwhm_widths": widths_x,
        "fwhm_left_xs": left_hm_xs,
        "fwhm_right_xs": right_hm_xs
    }


    # Save max peak information to CSV
    print("Save Peak information to CSV? ", peak_csv)
    if params != None and params["peak_csv"] == "y":
        file_name   = params["peak_file_name"]
        label       = params["peak_label"]
        timestamp   = params["peak_timestamp"]
        # Construct pandas DataFrame
        peak_dict = {
            "Label": [label],
            "Timestamp": [timestamp],
            "Peak Depth": [max_peak_depth],
            "Wavelength": [max_peak_x],
            "FWHM (pm)": [max_peak_fwhm]
        }
        peak_df = pd.DataFrame(data=peak_dict)

        os.makedirs(os.path.join("Test Results", "Peak Analyses"), exist_ok=True)
        csv_path = os.path.join("Test Results", "Peak Analyses", file_name)
        peak_df.to_csv(csv_path, index=False, mode='a', header=not os.path.exists(csv_path))    
        print("Saved to a file: ", file_name, "\n")


    return peak_info