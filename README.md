# WavelengthSweep & PlotSweep

- `WavelengthSweep.exe` can operate Keysight instruments (Tunable Laser Source and Optical Power Meter). Users can configure and save parameters. Measurement is analyzed and visualized. The raw data and peak analysis can be exported to CSV.
- `PlotSweep.exe` is a standalone executable to plot a saved raw data.

---

## Installation

After downloading the `.zip`, **unblock it before extracting**:

1. Right-click the downloaded `.zip` → **Properties**.
2. Check **Unblock** at the bottom → **OK**.
3. Now extract the `.zip`.

All apps (`WavelengthSweep.exe`, `PlotSweep.exe`) live in the same folder and share a single `_internal` directory — keep them together.

---

## Usage

### Run a test

1. Run `WavelengthSweep.exe`.
2. A configuration window will appear. Enter the desired settings (start wavelength, stop wavelength, etc.) manually, or load a preset.
3. Click **Save**. The program will check whether parameters are valid, and calculate the log count and the averaging time. The given step size may be slightly reduced to ensure the averaging time is an integer value.
4. Click **Run (or press Enter)**. The input window will close and the sweep will begin. A result window will appear with the results.
5. After the result window is closed, the program returns to step 1.

---

### Analyzing measurement

**Detecting Peak(s)**

- Simple peak analysis (depth, FWHM) is included.

**Plotting**

- The default plotting backend is **Plotly** (`matplotlib` is dropped since the version 20260527).

---

### Saving Results to CSV

Users can save raw data and/or peak data to a CSV file.

**Save Raw Data**

- Parameters are saved in the first line.
- Raw data includes wavelength (nm) and power (dBm) values.

**Save Peak Analysis**

Following fields are saved in the CSV file.

- Date, Wavelength (nm), Label, I.L., Depth, Width (pm), Temperature
- I.L. and Temperature can be left empty.

---

### Run subsequent tests (until program is quit)

- Parameters for the last test are saved and fields are greyed.
- To run another test with the same parameters, just click **Run or press Enter**.
- To change parameters, click **Change**.

---

### Load/Save/Delete Preset

- The program attempts to read `preset.csv` on startup. This file must be located in the same directory as `.exe` files. Because a new build `.zip` do not include `preset.csv`, copy the file from previous location.
- Once parameters are **saved** (in that, they passed checks), **Manage Presets...** button is activated. In the pop-up, users can replace an existing preset with the currently saved parameters, create a new preset with them, or delete an existing preset.

---

### Read Power in real-time

- Once parameters are **saved**, **Read Power...** becomes active. In the pop-up, the current powers for all four channels are measured and shown in two units(dBm and W), and updated every second.
- Power range setting is automatically adjusted.
- Parameters for source power and wavelength are referred from the saved parameters: **TLS Power (dBm), Stop Wavelength (nm)**, respectively.

### Reference

- Once a measurement is taken, it can be set a reference for subsequent measurements, by clicking **"Set Reference"**. To unset the reference, click **"Unset Reference"**.
- Because the parameters must be same for both reference and subsequent measurements, clicking **"Change"** button is assumed that the user would change parameters. Thus it immediately invalidates the existing reference and user should take a new measurement.
- For subsequent measurements, the reference and the new measurement spectra will be shown together in the result window. Both are unmodified.
- Difference between the new measurement and the reference is calculated element-by-element. The minimum is taken as the insertion loss.

### Multiple input channels

- Users can select input channels by selecting checkboxes up to 4. At least one must be selected.
- Peak analysis is performed only for a single channel with the least channel number.

### Pass/Fail Criteria

- Users can enter a range (min, max) for peak wavelength, depth, and width. It is saved together with the preset.
- All fields are 0 by default. If nothing is set, the result is not examined, and no message is shown.
- If a wavelength range is not set but either the depth or width range is set, the test always fails.
- If multiple peaks fall within the wavelength range, the peak with the deepest depth is chosen for examination.
- If a depth range is not set, it is skipped. The same applies to the width.
- If the wavelength range finds a peak, the row is highlighted in blue in the peak table. It is also automatically selected in the peak list in "Save peak info...".