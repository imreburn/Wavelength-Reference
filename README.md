# SingleSweep (Beta_20260512)

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

Raw data includes wavelength and power values.

- Select `y` for "Save raw data to CSV?"
- Enter a file name (without the `.csv` extension). A timestamp will be automatically appended to the file name.
- Data will be saved under `Test Results/Raw Data`.

**Save Peak Analysis**

Information about the highest peak (depth, wavelength (nm), and FWHM (pm)) can be saved to a file.

- Select `y` for "Save peak analysis to CSV?"
- Enter a file name (without the `.csv` extension). If the file already exists, a new entry will be appended.
- Enter a label if needed.
- A timestamp will be automatically included as a field.

---

## Peak Analysis and Plotting (Limited)

The current version has limited functionality for peak analysis and plotting.

**Detecting Peak(s)**

- Peak analysis (depth, FWHM) works for simple cases where the data contains well-defined peaks against a flat baseline.
- The algorithm detects the peak and its corresponding left and right bases. Peak depth is currently calculated as the greater of the two differences: `max(peak − left_base, peak − right_base)`. As a result, the depth of the highest peak corresponds to the global Max−Min of the dataset.

**Plotting**

- The default plotting backend is **matplotlib**.
- Support for **Plotly** as an alternative backend is under development and is not functional in this beta version.
