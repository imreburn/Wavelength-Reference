import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import find_peaks, peak_widths


def simple_analysis(df):

    x = df["Wavelength"]
    y = df["Power"]
    y_values = y.to_numpy()

    # Find peaks
    simple_prominence = (y.max() - y.min())*(3/4)
    max_indices, peak_properties = find_peaks(y, prominence=simple_prominence, distance=8000)

    # Wavelengths (nm) of peaks
    peak_wavs = [w*1e9 for w in x.iloc[max_indices].to_list()]
    print("Peak wavelenghs:", [f"{wx:.3f} nm" for wx in peak_wavs])

    # Find FWHM
    widths, width_heights, left_ips, right_ips = peak_widths(y_values, max_indices, rel_height=0.5)

    fwhm = []   # pm
    for n, (peak_idx, lx, rx, wx) in enumerate(zip(max_indices, left_ips, right_ips, widths), start=1):
        # print(f"Peak {n}: peak index={peak_idx}, left x={round(lx)}, right x={round(rx)}, width={(x.iloc[round(rx)]-x.iloc[round(lx)])*1e12:.3f}")
        fwhm.append((x.iloc[round(rx)]-x.iloc[round(lx)])*1e12)
    
    print("FWHM: ", [f"{fw:.3f} pm" for fw in fwhm])

    rounded_left = [round(lx) for lx in left_ips]
    rounded_right = [round(rx) for rx in right_ips]

    # Find peak heights
    widths2, width_heights2, left_ips2, right_ips2 = peak_widths(y_values, max_indices, rel_height=1)

    rounded_left2 = [round(lx) for lx in left_ips2]
    rounded_right2 = [round(rx) for rx in right_ips2]

    bases = []
    for _, (lx, rx) in enumerate(zip(rounded_left2, rounded_right2)):
        bases.append((y.iloc[rx]+y.iloc[lx])/2)

    peak_y = y.iloc[max_indices].to_list()

    peak_height = []
    for _, (lx, rx) in enumerate(zip(bases, peak_y)):
        peak_height.append(rx-lx)
    
    print("peak heights: ", [f"{h:.3f}" for h in peak_height])

    # Plot
    plt.figure(figsize=(12,6))
    plt.plot(x, y)
    plt.plot(x.iloc[max_indices], y.iloc[max_indices], "o")

    # Markers for FWHM
    plt.plot(x.iloc[rounded_left], y.iloc[rounded_left], '>')
    plt.plot(x.iloc[rounded_right], y.iloc[rounded_right], '<')

    # Markers for bases
    plt.plot(x.iloc[rounded_left2], y.iloc[rounded_left2], '>', mfc='g', ms=10)
    plt.plot(x.iloc[rounded_right2], y.iloc[rounded_right2], '<', mfc='r', ms=10)

    plt.xlabel("Wavelength")
    plt.ylabel("Power")
    plt.gca().invert_yaxis()
    # plt.legend()
    plt.grid(True)
    plt.show()



def plot_data(df):

    x = df["Wavelength"]
    y = df["Power"]

    x_values = x.to_numpy()
    y_values = y.to_numpy()

    # Find local maxima
    # Estimate a rolling baseline. This works better when the idle level slowly drifts.
    # Increase or decrease the window size depending on how slowly the baseline changes.
    window_size = 2000
    baseline = y.rolling(window=window_size, center=True, min_periods=1).median()
    print("Using rolling baseline with window size:", window_size)

    # Subtract the rolling baseline from the signal
    corrected_y = y - baseline

    max_indices, _ = find_peaks(corrected_y, prominence=0.1)
    print("Max indices:", max_indices)

    # Measure each peak width at half of the local peak height on the baseline-corrected signal.
    # left_ips and right_ips are fractional sample indices where the signal crosses half height.
    widths, width_heights, left_ips, right_ips = peak_widths(corrected_y.to_numpy(), max_indices, rel_height=0.5)

    # Convert fractional sample indices to x-values by linear interpolation.
    left_x = [x_values[i] + (x_values[i + 1] - x_values[i]) * (ip - i) for ip in left_ips for i in [int(ip)] if i < len(x_values) - 1]
    right_x = [x_values[i] + (x_values[i + 1] - x_values[i]) * (ip - i) for ip in right_ips for i in [int(ip)] if i < len(x_values) - 1]
    peak_width_x = [rx - lx for lx, rx in zip(left_x, right_x)]

    sample_index = np.arange(len(x_values))
    left_x2 = np.interp(left_ips, sample_index, x_values)
    right_x2 = np.interp(right_ips, sample_index, x_values)

    print("Left half-height fractional sample index:", left_ips)
    print("Right half-height fractional sample index:", right_ips)
    print("Left half-height x:", left_x)
    print("Right half-height x:", right_x)
    print("Left half-height x by np.interp:", left_x2)
    print("Right half-height x by np.interp:", right_x2)
    print("Peak widths in x units:", peak_width_x)
    peak_heights = corrected_y.iloc[max_indices].to_numpy()

    # Plot x-y graph
    plt.plot(x, y, label="Signal")
    plt.plot(x.iloc[max_indices], y.iloc[max_indices], "o", label="Local Peak")
    plt.plot(x, baseline, linestyle="--", label="Rolling Baseline")

    # Draw half-height width markers for each peak on the original signal.
    for peak_idx, left_idx, right_idx, half_height in zip(max_indices, left_ips, right_ips, width_heights):
        peak_base = baseline.iloc[peak_idx]
        y_half = peak_base + half_height

        left_i = int(left_idx)
        right_i = int(right_idx)

        if left_i < len(x_values) - 1 and right_i < len(x_values) - 1:
            left_x_val = x_values[left_i] + (x_values[left_i + 1] - x_values[left_i]) * (left_idx - left_i)
            right_x_val = x_values[right_i] + (x_values[right_i + 1] - x_values[right_i]) * (right_idx - right_i)
            plt.hlines(y_half, left_x_val, right_x_val, linestyles="--", label="Half Height Width" if peak_idx == max_indices[0] else "")

    # Label each peak with height above baseline and width.
    for n, (peak_idx, height, width_x) in enumerate(zip(max_indices, peak_heights, peak_width_x), start=1):
        peak_x = x.iloc[peak_idx]
        peak_y = y.iloc[peak_idx]
        label_text = f"P{n}\nlambda={peak_x*1e9:.6g}\ndy={height:.3g}dB\ndx={width_x*1e12:.3g}pm"
        plt.annotate(
            label_text,
            xy=(peak_x, peak_y),
            xytext=(0, -12),
            textcoords="offset points",
            ha="center",
            va="top"
        )

    plt.xlabel("Wavelength")
    plt.ylabel("Power")
    plt.gca().invert_yaxis()
    plt.legend()
    plt.grid(True)
    plt.show()


    # print("Peak x values:", x.iloc[max_indices].to_list())
    # print("Peak heights above baseline:", corrected_y.iloc[max_indices].to_list())
    # print("Peak values:", y.iloc[max_indices].to_list())
    # print("Baseline at peak positions:", baseline.iloc[max_indices].to_list())
    # for n, (peak_idx, lx, rx, wx) in enumerate(zip(max_indices, left_x, right_x, peak_width_x), start=1):
    #     print(f"Peak {n}: peak index={peak_idx}, left x={lx}, right x={rx}, width={wx}")


