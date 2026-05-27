# Changelog

## [Unreleased]

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
