import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
from scipy.signal import find_peaks, peak_widths

# Plain plot with matplotlib
# def matplotlib_plain(df):
#     plt.plot(df["Wavelength"], df["Power"])
#     plt.show()

# Analyze peak(s)
def peak_analysis(df, params=None):
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
    d_x         = x.iloc[1] - x.iloc[0]
    
    # Find peaks
    # tunable parameters: prominence, distance
    # Assume a peak should be deeper than 3/4 of global max-min
    simple_prominence = (y.max() - y.min())*(3/4)
    peak_indices, peak_properties = find_peaks(y, prominence=simple_prominence, distance=8000)

    

    # These are actual indices
    peak_prominences    = peak_properties['prominences']
    left_bases          = peak_properties['left_bases']
    right_bases         = peak_properties['right_bases']
    
    # Find peak depths
    peak_depths = [max(p-l, p-r) for p, l, r in zip(y.iloc[peak_indices], y.iloc[left_bases], y.iloc[right_bases])]

    # Find FWHM
    # left_ips, right_ips are fractional indices
    widths, width_heights, left_ips, right_ips = peak_widths(y, peak_indices, rel_height=0.5, prominence_data=(peak_prominences, left_bases, right_bases))

    # Convert fractional indices in x-axis
    left_hm_xs  = [x.iloc[int(ip)] + (ip % 1.0) * d_x for ip in left_ips]
    right_hm_xs = [x.iloc[int(ip)] + (ip % 1.0) * d_x for ip in right_ips]
    widths_x = [(w * d_x)*1e12 for w in widths] # convert to picometer

    # Get max peak
    max_peak_num    = np.argmax(peak_prominences)
    max_peak_depth  = max(peak_depths)
    max_peak_x      = x.iloc[peak_indices[max_peak_num]]*1e9
    max_peak_fwhm   = widths_x[max_peak_num]
    
    # Construct pandas DataFrame
    peak_dict = {
        "Label": [label],
        "Peak Depth": [max_peak_depth],
        "Wavelength": [max_peak_x],
        "FWHM": [max_peak_fwhm]
    }
    peak_df = pd.DataFrame(data=peak_dict)

    # Save max peak information to CSV
    print("Save Peak information to CSV? ", peak_csv)
    if peak_csv == "y":
        os.makedirs("Test Results-Peak", exist_ok=True)
        csv_path = os.path.join("Test Results-Peak", file_name)
        peak_df.to_csv(csv_path, index=False, mode='a', header=not os.path.exists(csv_path))    
        print("Saved to a file: ", file_name)

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

    return peak_info

# Plot with matplotlib
def plot_matplotlib(df, peak_info=None):
    x = df["Wavelength"]
    y = df["Power"]

    # Plot raw data
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.subplots_adjust(bottom=0.2)
    ax.plot(x, y)
    
    if peak_info != None:
        peak_indices        = peak_info["peak_indices"]
        peak_depths         = peak_info["peak_depths"]
        peak_left_bases     = peak_info["left_bases"]
        peak_right_bases    = peak_info["right_bases"]
        fwhm_heights        = peak_info["fwhm_heights"]
        fwhm_left_xs        = peak_info["fwhm_left_xs"]
        fwhm_right_xs       = peak_info["fwhm_right_xs"]
        fwhm_widths         = peak_info["fwhm_widths"]

        # print("Peak information received")
        ax.scatter(x.iloc[peak_indices], y.iloc[peak_indices], marker='p')

        # # Markers for FWHM
        ax.scatter(fwhm_left_xs, fwhm_heights, marker='>')
        ax.scatter(fwhm_right_xs, fwhm_heights, marker='<')

        # Markers for bases
        ax.scatter(x.iloc[peak_left_bases], y.iloc[peak_left_bases], marker='>')
        ax.scatter(x.iloc[peak_right_bases], y.iloc[peak_right_bases], marker='<')

    ax.set_xlabel("Wavelength")
    ax.set_ylabel("Power")
    ax.invert_yaxis()
    # ax.legend()
    ax.grid(True)

    peak_text = ""

    for n, (pw, pd, fw) in enumerate(zip(x.iloc[peak_indices], peak_depths, fwhm_widths), start=1):
        peak_text += f"Peak {n}: Wavelength={pw*1e9:.7f} nm, Depth={pd:.4f}, FWHM={fw:.4f} pm\n"

    fig.text(0.5, 0.05, peak_text, ha='center', va='center')

    plt.show()

# Plot with plotly
def plot_plotly(df, peak_info=None):
    fig = px.line(df, x="Wavelength", y="Power")
    fig.show()

def analyze(df, params):
    peak_info = peak_analysis(df, params)
    
    if params["plot_backend"] == "plotly":
        plot_plotly(df, peak_info)
    else:   # matplotlib
        plot_matplotlib(df, peak_info)
