# Changelog

## [Unreleased]

### Added

- Validation checks for input values.
- Two FWHMs (max, avg) can be shown on the plot.

### Changed

- A dropdown list for sweep speed field. TLS does not accept other values.
- A padding (currently set as 10 pm) is added to start/stop wavelength. Data within this area will not be used for finding peaks and plotting.
- Create a subfolder for each day when saving raw data (not peak information).

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

- Add +1 to the number of data to be logged

## [Beta_20260512] - 2026-05-12

### Added

- First beta release.
