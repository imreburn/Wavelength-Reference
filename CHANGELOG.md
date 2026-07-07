# Changelog

## [Unreleased]

### Added

- Keyboard shortcut (`p`) for "Read Power(p)..." button. ([#61](https://github.com/imreburn/Wavelength-Reference/issues/61))
- "Save peak info" window shows the wavelength, depth and width of the selected peak and insertion loss.([#57](https://github.com/imreburn/Wavelength-Reference/issues/57))

### Changed

- The name of y-axis changes to "Power (dBm or dB)", and "(dBm)" or "(dB)" is appended to the legend of each spectrum.([#56](https://github.com/imreburn/Wavelength-Reference/issues/56))

### Fixed

- The range setting for the power meter cannot be lower than -70 dBm, but the program allowed this. Now the config window gives an error message.
- Prevent an error when the power meter readout rarely gives a saturated value or fails to read.
- Fixed a bug ([#62](https://github.com/imreburn/Wavelength-Reference/issues/62))

## [v1.1.6] - 2026-06-30

### Added

- "Max Power (W)" column is added in the power readout window. It shows the maximum power recorded for each channel while the window is open.

### Changed

- Change the date format. (yyyy-mm-dd -> mm/dd/yyyy)
- The default prominence threshold for finding peaks has changed. (75 % -> 50 %)

### Fixed

- Fixed a bug that when a label for a peak is entered with only numbers with leading zeros, they will be wiped out when reading the CSV file.

## [1.1.5] - 2026-06-29

### Added

- Users can optionally input pass/fail criteria for a test. The result is displayed in the figure window.

### Changed

- "Read Power..." reads the power meter at a faster rate (10 Hz -> 20 Hz).
- The unit of the absolute power is chosen automatically.

### Fixed

- Fixed a bug that a preset cannot be loaded if it is newly created by "Manage Presets..." and the user tries to load it after clicking "Change". Now it can be loaded right after the save.
- "Read Power..." button cannot be pushed while the power readout window is open.

## [v1.1.4] - 2026-06-23

### Added

- Added 5 filters to smooth data.
- Bind 'p' key to the "Save peak info..." button.

### Changed

- "Read Power..." reads the power meter at a faster rate (1 Hz -> 10 Hz).
- Some buttons on the right side of the result window moved to the top bar.
- Updated the icon.
- When a reference is set, the subtracted data (measured - reference) is shown by default. Raw data and the reference data are hidden at first, and can be shown via clicking the legends.

### Fixed

- Fixed a bug that right click dragging reverses the inverted y-axis. When this happens, users can click 'autoscale' or 'reset axes' button.

## [v1.1.3] - 2026-06-22

### Added

- Executables now use the company logo as their icon.

### Changed

- Logs and CSV files (preset and data) are now saved to the fixed folder `C:\Users\mikea\OneDrive\Desktop\DataSweep`, instead of a separate folder for each version. The path is written in `data_dir.txt` and users may modify.

## [v1.1.2] - 2026-06-18

### Changed

- Information about Delta markers are displayed as a table. For the first marker, delta values are calculated with respect to the origin.

### Fixed

- Fixed the bug related to "Max points(x1000)/plot" button. It is active and users can set the maximum number of points per plot for sampling. Actual number is multiplied by 1000. Default value is 10. (10k points per plot)

## [v1.1.1] - 2026-06-18

### Added

- A preset can be saved via "Manage Preset...". It may replace an existing preset or create a new one. The user also can delete an existing preset.
- "Change" button is added in the config window. Pushing it invalidates existing configuration and reference if previously set.
- Supports multi channels. Measurements from all channels will be plotted in a single window. Data analysis (peak detection and insertion loss) is performed for one channel (the smallest channel number).
- "Read Power..." button is added in the config window. After parameters are checked and saved, the button is activated. A new window appears and shows power for all channels in every second.
- "Repeat" button (or press Enter) is added in the plot window. Clicking this button closes the plot window and clicks "Run" button in the config window automatically.

### Changed

- Now **WavelengthSweep** includes **RefSweep**. Users can set the last measurement as a reference spectrum.
- When a reference is set, the subsequent measurements are plotted as raw data, instead of being subtracted by the reference.
- Insertion loss value is shown on the spectrum below the marker.
- The "Clear markers" button moved below the Click Mode.
- "Show markers" can also control "I.L" marker if exists.
- Units are removed from Delta mode markers.

### Fixed

- Fixed an error that the power of cell was saved for the insertion loss when saving peak data.
- Fixed a Runtime warning where measured power is less than or equal to 0.
- Fixed an issue that the GUI window looks fuzzy at start.

## [v1.0.2] - 2026-06-12

### Added

- GUI window grabs keyboard focus.

## [v1.0.1] - 2026-06-10

### Added

- "Enter" key will start a run when 'Run' button is enabled.
- RefSweep: overlays include the absorption data before subtracted to the reference.

### Changed

- '0' Step size will be adjusted automatically, instead of a warning message.
- TLS will stay at the stop wavelength after the sweep.

### Fixed

- Fixed an issue that field names are not fully shown in the GUI window.

## [v1.0.0] - 2026-06-10

### Added

- Support reference sweep via `RefSweep`.
- Support dynamic range scans.
- Logging is added to capture messages and errors.
- Reference data is plotted after taking reference data.
- Initial Power meter Range (dBm), Dynamic Scans, Decrement (dB) fields are added. These fields are also added in `preset.csv`
- Raw Data CSV files include the testing parameters at the first line.

### Changed

- Saving peak data: File saving prompt is skipped if reusing an existing file.
- Saving peak data: A new entry replaces an existing one only if the label is the same AND the wavelength is close by. (0.5nm)
- Saving peak data: The last chosen file is selected by default while the program is running.
- Saving peak data: The last used label, temperature is remembered while the program is running.
- The user doesn't need to push 'Save' button again if the user wants to run a test with the same setting used in the last run. First launch of the program still requires 'Save'.
- (x, y) of peak bases is shown on the plot. It is removed from the peak table.

### Removed

- The reset button is removed from the GUI input window.

## [20260602] - 2026-06-02

### Added

- 'I.L.' and 'Temperature' fields are added when saving peak data to a CSV file. They can be left empty.
- When saving peak data to a CSV file, the user can choose an existing CSV file in the figure or create a new file. The filename/path can still be changed in the standard file saving dialog.

### Changed

- Moved two FWHM columns next to the corresponding depth column in the peak table in the figure.
- Saving raw data and peak information to CSV files has been moved from the GUI input window to the plotting window.
- It no longer automatically creates a subfolder for each day when saving raw data to CSV.
- A custom peak can be created from user-clicked markers.
- The user can select which peak to save, including the user-created peak. The peak with the maximum depth (max) is chosen by default.
- Renamed Mode 1 and Mode 2 as Delta and Bandwidth, respectively.
- The figure window is maximized automatically.
- Plotly uses SVG instead of WebGL.
- The 'Clear markers' button clears both Delta and Bandwidth markers.
- The checkboxes under 'Show markers' can turn markers of peaks/bases and FWHM markers on and off.
- The 'Timestamp' column in the peak data CSV has been renamed to 'Date' and includes a datestamp, instead of a timestamp.
- When saving peak data to a CSV file, new data replaces the existing entry whose label is the same as the new data in the same file. A warning to replace an existing file is shown, and it is okay.

## [20260601] - 2026-06-01 Quick Fix

### Fixed

- Fixed the issue that figure reuses the data from the first run.
- Handled the case that an error is shown when no peak is found.

## [20260527] - 2026-05-27

### Added

- Validation checks for input values.
- Two FWHMs (max, avg) can be shown on the plot.
- Added Click Mode 2 and a marker at the clicked location.
- Added a slider for fine adjustment of the marker position under Click Mode 2.
- Added two markers with an offset in the y-axis.
- Downsampling the plot. The graph remains detailed when zoomed in.
- Peak information is shown as a table in the figure.

### Changed

- A dropdown list for sweep speed field. TLS does not accept other values.
- A padding (currently set as 50 pm, same as KeySight application) is applied to the start/stop wavelength. Data within this area will not be used for finding peaks and plotting.
- Creates a subfolder for each day when saving raw data (not peak information).
- Saving to CSV is handled in a separate function.
- Replaced Pandas with NumPy (mostly).
- Global variables changed to use a dataclass.

### Deprecated

- Plotly will be the only backend for plotting. Matplotlib will be dropped.

## [20260520] - 2026-05-20

### Added

- Plotly support.
- Error handling when connecting instruments.
- Check if any error from the error queue for each instrument.
- Standalone executable for plotting.

### Changed

- Step size turns red only when the value has been adjusted.
- Numbers no longer use scientific notation; they are displayed in commonly used units.
- Plotly is now the default backend for plotting.

### Fixed

- Added +1 to the data point count to ensure correct logging.

## [Beta_20260512] - 2026-05-12

### Added

- First beta release.
