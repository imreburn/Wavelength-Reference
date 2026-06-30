# WavelengthSweep & PlotSweep

- `WavelengthSweep.exe` can operate Keysight instruments (Tunable Laser Source and Optical Power Meter). Users can configure and save parameters. Measurement is analyzed and visualized. The raw data and peak analysis can be exported to CSV.
- `PlotSweep.exe` is a standalone executable to plot a saved raw data.

---

## Download & Install

The latest version can be downloaded from **Releases** on the right side. It is compressed as a single `Sweeps-vx.x.x.zip` file. I would advise to download it to where it is not synced in a cloud. Instead, shortcuts can be created and placed in Desktop after extracting it (Please read the following instructions before extracting).

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

### Config Window

- See [docs/config.md](docs/config.md) for more information.

### Figure Window

- See [docs/figure.md](docs/figure.md) for more information.

---

### Data Location

- The path to the data folder that stores presets, logs and data is written at `datapath.txt`, which must be placed at the same path as executables (not shortcuts).
- Data folder may be placed in a cloud-synced location to access data.

---

### Run a test repeatedly (until program is closed)

- Parameters for the last test are saved and fields are greyed.
- To run another test with the same parameters, just click **Run or press Enter**.
- To change parameters, click **Change**.
- To do this even faster, users can click **Repeat or press Enter** in **the figure window**. Doing it closes the figure window, and click Run button in the config window automatically.
