# SingleSweep (ver_20260602)

`SingleSweep.exe` performs repeated single continous sweep and measures power, with configurable parameters. Measurement is analyzed and visualized. The raw data and peak analysis can be exported to CSV. 

## Usage

### Overall

1. Run `SingleSweep.exe`.
2. A configuration window will appear. Enter the desired settings (start wavelength, stop wavelength, etc.) manually, or load a preset. The last-used configuration is retained for the duration of the session.
3. Click **Save**. The program will calculate the number of data points to be logged and the averaging time. The given step size may be slightly reduced to ensure the averaging time is an integer value.
4. Click **Run**. The configuration window will close and the measurement will begin. A graph window will appear with the results.
5. After the user closes the graph window, the program returns to step 1.

---

### How to Use Presets

- The program attempts to read `preset.csv` on startup. This file must be located in the same directory as `SingleSweep.exe`.
- To add a preset, open the file in a text editor and add a new line with a name and the corresponding values, separated by commas with no spaces.
- **Preset parameters:** Name, Start Wavelength (nm), Stop Wavelength (nm), Sweep Speed (nm/s), Step Size (pm), TLS Power (dBm)

---

### Saving Results to CSV

Users can save raw data and/or peak analysis results to a CSV file.

**Save Raw Data**

Raw data includes wavelength (nm) and power (dBm) values.

**Save Peak Analysis**

Following fields are saved in the CSV file.

- Date, Wavelength (nm), Label, I.L., Depth, Width (pm), Temperature
- I.L. and Temperature can be left empty.

---

## Peak Analysis and Plotting

**Detecting Peak(s)**

- Peak analysis (depth, FWHM) works for simple cases where the data contains well-defined peaks.

**Plotting**

- The default plotting backend is **Plotly** (matplotlib is dropped since the version 20260527).
- `PlotSingle` is a standalone executable to plot a saved raw data. It also can plot CSV files saved from KeySight software.
