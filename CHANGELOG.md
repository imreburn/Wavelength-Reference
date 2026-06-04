# Changelog

## [Unreleased]

## Added

- Simple logging is added to capture runtime errors.

## Changed

- Saving peak data: File saving prompt is skipped if reusing an existing file.
- Saving peak data: A new entry replaces an existing one only if the label is the same AND the wavelength is close by. (0.5nm)


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
