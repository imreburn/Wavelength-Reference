import pandas as pd
import matplotlib.pyplot as plt

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

        for n, (pw, pd, fw) in enumerate(zip(x.iloc[peak_indices], peak_depths, fwhm_widths), start=1):
            peak_text += f"Peak {n}: Wavelength={pw*1e9:.7f} nm, Depth={pd:.4f}, FWHM={fw:.4f} pm\n"

    ax.set_xlabel("Wavelength")
    ax.set_ylabel("Power")
    ax.invert_yaxis()
    # ax.legend()
    ax.grid(True)

    peak_text = ""



    fig.text(0.5, 0.05, peak_text, ha='center', va='center')

    plt.show()