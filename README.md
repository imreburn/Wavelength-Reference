- [WavelengthSweep \& PlotSweep](#wavelengthsweep--plotsweep)
  - [Download \& Install](#download--install)
  - [Usage](#usage)
    - [Quick start guide](#quick-start-guide)
    - [Config window](#config-window)
    - [Graph window](#graph-window)
    - [Data location](#data-location)


# WavelengthSweep & PlotSweep

- `WavelengthSweep.exe` can operate Keysight instruments (Tunable Laser Source and Optical Power Meter). Users can configure and save parameters. Measurement is analyzed and visualized. The raw data and peak analysis can be exported to CSV.
- `PlotSweep.exe` is a standalone executable to plot a saved raw data.

---

## Download & Install

The latest version can be downloaded from **Releases** on the right side. It is compressed as a single `Sweeps-vx.x.x.zip` file. It is recommended to download it to where it is not synced in a cloud. Instead, shortcuts can be created and placed in Desktop after extracting it. Please read the following instructions before extracting.

After downloading the `.zip`, **unblock it before extracting**:

1. Right-click the downloaded `.zip` → **Properties**.
2. Check **Unblock** at the bottom → **OK**.
3. Now extract the `.zip`.

All apps (`WavelengthSweep.exe`, `PlotSweep.exe`) live in the same folder and share a single `_internal` directory — keep them together.

---

## Usage

### Quick start guide

1. Run `WavelengthSweep.exe`.
2. A [config window](docs/config.md) will appear. Enter the desired parameters (start wavelength, stop wavelength, etc.) manually, or load a preset.
3. Click **Save**. Parameters are checked, and the log count and the averaging time are calculated. If the given parameters does not pass checks, an error message will be displayed. Provided that parameters are okay, Run button will be active.
4. Click **Run (or press Enter)**. The config window is closed and the sweep begins. A [graph window](docs/graph.md) will appear.
5. After the graph window is closed, and the config window shows up again. The last used parameters are saved, and it is ready to run another test with the same parameters (step 4). If the user wants to change parameters, click the **Change** button (step 2).
6. Closing the config window exits `WavelengthSweep`.
   
---

### Config window

- See [docs/config.md](docs/config.md) for more information.

### Graph window

- See [docs/graph.md](docs/graph.md) for more information.

---

### Data location

- `data_dir.txt` contains the path to the data folder, which stores presets, logs and data. Users may change the path. `data_dir.txt` must be located at the same path as the executables (not shortcuts).
- `C:\Users\mikea\OneDrive\Desktop\DataSweep` is the default path written in the `data_dir.txt`. Users may change the path. The path should be a folder, and it will be created if not exists. But the parent folder must exist. 
- Data folder may be placed in a cloud-synced location to access data.