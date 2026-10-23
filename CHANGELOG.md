# Changelog

## [Unreleased]

### Added

- In the config window, "Peak Test Criteria" has a new "Base" dropdown: max (the default), avg, or min. It sets the base the peak test measures depth and width from.

### Changed
- In the graph window, the label (SN) moved from above the plot to a field in the right panel, where you can change it. "Save raw data" and "Save peak info" use the changed label.
- If only the label's counter is changed there, the config window's counter continues from it. Any other change stops "Close & Repeat" at the config window with a message.
- "Save peak info" saves to Excel files (.xlsx) instead of CSV files. In its table, you pick the columns and their decimals, and you can save several peaks at once.
- In "Save peak info", the File menu has "New file", "Open file…" to pick a file in any folder, and your recent files. It no longer lists every file in the Peaks folder.
- In the graph window's dialogs, Esc in a text box now only leaves the box. Press Esc again to close the dialog.
- In the graph window, "Depth (dB)" in the Peak table (under Max base, Avg base and Min base) and in the Peak test result now shows 3 decimal places by default instead of 2. In "Save peak info", the Depth columns also start with 3 decimal places.
- In the config window, "Peak Test Criteria" is laid out as a table: "min" and "max" are column headers instead of labels on every row.
- Presets are now saved in TOML files (`preset_N7778C.toml`, `preset_81600B.toml`) instead of CSV files, in the same folder. The first time the config window opens for a source, its presets are moved from `preset_<source>.csv` to the new file, and the CSV is renamed to `preset_<source>.csv.bak`.

### Fixed

- A preset file the program can't read is no longer overwritten. The config window shows the error, with the line and column, and "Manage Presets..." stays off until the file is fixed. Before, saving a preset could replace such a file and lose the other presets.

## [2.0.4] - 2026-10-19

### Added

- In the config window, a new "Detector" row below "Source" shows the power meter, N7748A. It's also listed in the graph window's "Sweep info" and saved in the first line of raw data files.
- Keyboard shortcuts in the config window: R checks or unchecks "Use reference", and L checks or unchecks "Laser on" in the Power Readout. The checkboxes are now labeled "Use reference (R)" and "Laser on (L)".

### Changed

- The pass/fail test is now called the peak test.
  - In the config window, the "Pass/Fail Criteria (Optional)" section is renamed to "Peak Test Criteria (Optional)".
  - In the graph window, the "Pass/Fail test result" table is renamed to "Peak test result". 
  - The tested peak's note in the Peak table and in "Save peak info" is now "tested" instead of "criteria". 
  - In "Sweep info", the "Pass/fail criteria" group is now "Peak test criteria".
- In the config window, "Wavelength" in field names is now "λ"
- In the config window, "λ Padding (pm)" moved up, between "λ Stop (nm)" and "Sweep Speed (nm/s)".
- In the config window, "Laser Source" is renamed to "Source". In the graph window's "Sweep info", "Laser source" is now "Source" too.
- In the console, "Sweeping..." no longer repeats every second during a sweep. Instead, a single line shows the elapsed time and the config window's sweep time: "Laser busy... 5 s (Duration / Sweep: 2.04 s)". The laser takes a few seconds longer than "Duration / Sweep" because of its overhead.
- In the graph window, "|ΔP| (dB)" in the Delta table and "Depth (dB)" in the Custom peak table now show 3 decimal places by default instead of 2.

### Fixed

- Close & Repeat no longer starts the Power Readout in the config window, so the laser goes straight into the next sweep.

## [2.0.3] - 2026-10-12

### Added

- In the graph window, pressing Esc closes a popup. Their Cancel and Close buttons now show "(Esc)". ([#113](https://github.com/imreburn/Wavelength-Reference/issues/113))
- Added a "Close & Repeat (Enter)" button to the Power readout dialog. It closes the dialog and the graph window, then runs the same sweep again.
- In the graph window, pressing X resets the plot's zoom, the same as the "Autoscale" or "Reset axes" button in Plotly's modebar. ([#118](https://github.com/imreburn/Wavelength-Reference/issues/118))
- In the graph window, a new "Show / hide...(H)" button on the menu bar opens a popup that replaces the "Show markers/table" section. Choices carry over to the next plot while the program runs.
- In the graph window, Bandwidth click mode now places two markers: B1 (the peak) and B2 (the base). The first click places B1 and the second places B2. After that, clicks take turns moving them: the third click moves B1, the fourth moves B2, and so on. The custom peak's base is now B2 instead of the latest Delta marker, in the Custom peak table (headers "Peak (B1)" and "Base (B2)") and in "Save peak info". Delta markers no longer affect the custom peak. ([#120](https://github.com/imreburn/Wavelength-Reference/issues/120))
- In the Custom peak table, the "Bandwidth (pm)" column is now "Width (pm)", and a new "Amplitude (dB)" column next to it shows how far above B1 the width was measured.
- In the Peak table, a new "IL (dB)" column under a "Reference" header shows the sweep's insertion loss, the same value on every row. It appears only when a reference is used, sits between "Peak" and "Max base", and shows 1 decimal place by default.
- In the graph window, a new "Bandwidth mode" setting under Click mode chooses how the width of the peak is measured.:
  - "Automatic" (default): the width is measured at a percentage of the depth from B1 up to B2, set in "Bandwidth amplitude (%)" (1–99, default 50%). The search for the edges reaches as far from B1 as B2 is.
  - "Manual": the width is measured at "Bandwidth amplitude (dB)" above B1. The edges are searched for across the whole spectrum. If the amplitude is too large for the dip, no width is shown. The -/+ buttons on the "Bandwidth amplitude (dB)" field now change the value by 0.001 instead of 1. ([#107](https://github.com/imreburn/Wavelength-Reference/issues/107))
- In the graph window, the width markers and values appear only when both edges are found, so the two markers always sit at the same height. Otherwise a note under the Bandwidth fields explains why there's no width.

### Changed

- When saving raw data, the default file name is `<label>_<time>.csv` (or `<time>.csv` with no given label), instead of the fixed name `raw_data.csv`
- In the graph window, keyboard shortcuts now also work right after you click a checkbox or a radio button.
- In the config window, the "Set Reference" / "Unset Reference" button is now a "Use reference" checkbox. The status next to it now reads "No data" (black), "Data ready" (blue), or "In use" (red), instead of "Not Set / Not Available", "Not Set / Available", or "Set".
- In the graph window, the right panel's sections are renamed "Plot sampling" (was "Max points(x1000)/plot") and "Click mode" (was "Click Mode"). The "Show markers/table" section moved to the new "Show / hide" popup.
- In the graph window, Delta markers are now numbered D1, D2, … instead of M1, M2, …, on the plot and in the tables.
- In the graph window, the plot now fills the width of the window instead of a fixed width, and adjusts when the window is resized. The "Plot in Watt" window does the same.
- In the graph window, the "FWHM (max/avg/min base)" markers are renamed to "Width (max/avg/min base)".
- In the graph window, the Pass/Fail result is now a table titled "Pass/Fail test result", just above the Peak table, instead of a single line. ([#119](https://github.com/imreburn/Wavelength-Reference/issues/119)). Its "Customize..." dialog sets the decimal places of the measured values (by default 4 for λ, 2 for depth, 1 for width), and the choices carry over to the next plot while the program runs. It also shows when no peak is found or the peak table is hidden. ([#115](https://github.com/imreburn/Wavelength-Reference/issues/115))
- Plotly's modebar in the top-right corner of the plot is now always visible.
- In the config window, clicking Save now shows an error if the Pass/Fail Criteria set a peak depth or width range without a peak wavelength range. Before, the test then always failed in the graph window.
- In the config window, the parameter "TLS power (dBm)" can be left blank when an external laser source is selected, and the default also changes to blank. It is still required and set as 0.1 dBm when N7778C is selected.

### Removed

- In the graph window, the fine-tune slider for the Bandwidth marker and its "Slider range (pm)" field are removed.
- In the graph window, the "Search range (pm)" field is removed. Manual Bandwidth mode now searches the whole spectrum.

### Fixed

- Fixed a bug where pressing Enter in a dialog in the graph window (for example, on the file list in "Save peak info") closed the window and started the next sweep. Enter now runs "Close & Repeat" only from the main window or the Power readout dialog, and not while you're typing in a field or using a dropdown.
- Fixed a bug that the Pass/Fail result is not shown when no peak is found or the peak table is hidden. ([#115](https://github.com/imreburn/Wavelength-Reference/issues/115))


## [2.0.2] - 2026-09-28

### Added

- Added an info icon next to the "Label & Auto-Save" section title. Its popup explains how the section works.

### Changed

- Updated some explanations in the info popups.


## [2.0.1] - 2026-09-28

### Added

- Added info icons (a circled "i") next to some section titles. Clicking an icon opens a popup with more details. To close the popup, click "Close" or press Esc. More info icons may be added later. ([#104](https://github.com/imreburn/Wavelength-Reference/issues/104))
- Added a "Duration / Sweep (s)" field below the "Averaging Time (us)" field. It shows the total time per sweep, which is the averaging time multiplied by the log count.

### Fixed

- The "Laser on" checkbox in the "Power Readout" section is updated if the on/off button on the front panel is pushed by users.
- The fields in the "Label & Auto-Save" section no longer move when "Auto-save raw data" is turned on or off, or when the label changes. They now line up with the fields in the "Pass/Fail Criteria" section.


## [2.0.0] - 2026-09-23

### Added

- Supports the external laser source. This involves multiple changes, more information here:([#85](https://github.com/imreburn/Wavelength-Reference/issues/85))
- Added a "Close Window" button at the right end of the navigation bar in the graph window. Renamed the button "Repeat (Enter)" to "Close & Repeat (Enter)". ([#80](https://github.com/imreburn/Wavelength-Reference/issues/80))
- Added a "Sweep Info..." button in the graph window that shows the parameters of the current sweep. ([#97](https://github.com/imreburn/Wavelength-Reference/issues/97))
- Keyboard shortcuts (`s`, `f`, `i`, `w`) for the "Save Raw Data...(S)", "Apply Filter...(F)", "Sweep Info...(I)", and "Close Window (W)" buttons in the graph window.
- "Label & Auto-save (Optional)" section in the config window.
  - "Add label": builds a label from a prefix and an optional zero-padded counter (0-4 digits), with a live preview. The counter goes up by 1 on every Run, and Run is refused once it passes the digit limit.
  - "Auto-save raw data": saves the raw data to `Raw Data/<label>_<time>.csv` (or `<time>.csv` with no given label) after every sweep.
  - The label is shown above the top-left corner of the plot and pre-fills "Label (SN)" in the "Save peak info" window.
- A status line under the navigation bar in the graph window shows the latest save result (auto-save, "Save raw data...", "Save peak info...") with the file name.

### Changed

- The power measurements are no longer multiplied by -1. Instead, the raw measurement with its sign is preserved. Y-axis of the plot is no longer inverted as a result. This doesn't change any relative measurements such as depth and width. ([#90](https://github.com/imreburn/Wavelength-Reference/issues/90))
- Loading a preset now saves the parameters right away (locked, ready to Run). Pressing "Change" keeps the values but clears the preset name, so edited values are never run under the preset's name. Saving the current values with "Manage Presets..." (new or replaced) now shows that preset's name. ([#95](https://github.com/imreburn/Wavelength-Reference/issues/95))
- The sweep time is now recorded when Run is pressed (not Save), in the format `YYYY-MM-DD_HH-MM-SS`.
- Default setting for applying a filter is changed to ('Hamming', 40).
- [PlotSweep]: The program loops until no file is selected.
- Power readout ([#94](https://github.com/imreburn/Wavelength-Reference/issues/94))
  - Power readout is now shown on the config window directly, instead of a new pop-up window.
  - The user can turn on/off laser and control wavelength and power. The maximum measured power can be reset.
  - The same functionality is also added to the graph window. "Power Readout...(R)" button is added and its keyboard shortcut is `r`.

## [1.1.12] - 2026-09-09

### Added

- Added the "Wavelength Padding (pm)" parameter in the config window. This extra padding to the sweep range from (start wavelength - padding) to (stop wavelength + padding). The default value is 50 pm (same as the Keysight IL), but the user may change it to 0. ([#88](https://github.com/imreburn/Wavelength-Reference/issues/88)).

### Fixed

- Fixed the bug when the measured power is too low. ([#60](https://github.com/imreburn/Wavelength-Reference/issues/60))
- Display the loaded presets alphabetically ([#89](https://github.com/imreburn/Wavelength-Reference/issues/89))

## [v1.1.11] - 2026-07-22

### Added

- Log the counter for each sweep. ([#81](https://github.com/imreburn/Wavelength-Reference/issues/81))
- Added peak depth and FWHM (relative to the minimum baseline) to the auto-detected peak table and markers. More changes will follow in future updates. ([#84](https://github.com/imreburn/Wavelength-Reference/issues/84))

### Changed

- Applied the power meter's maximum averaging-time spec (10 s). ([#82](https://github.com/imreburn/Wavelength-Reference/issues/82))
- Applied the tunable laser source's maximum output power spec, which varies with the sweep range. ([#72](https://github.com/imreburn/Wavelength-Reference/issues/72))
- Merged the two FWHM marker sets into one and updated the legend names.

### Fixed

- Fixed incorrect combining of multiple scans.

## [v1.1.10] - 2026-07-17

### Added

- The application version is recorded in the parameters.

### Changed

- The reference status message "Not Set" has been split into two messages. **"Not Set / Available"** means a reference spectrum is available but has not been set, and **"Not Set / Not Available"** means **no** reference spectrum is available — either because the program was just launched, or because the "Change" button was pressed, invalidating the saved reference spectrum.
- The laser source is turned off when a run finishes or the power readout window is closed. ([#72](https://github.com/imreburn/Wavelength-Reference/issues/72))
- Units are now shown next to the "Pass/Fail Criteria" field names in the config window.
- The "Smooth data..." button in the figure window has been relabeled "Apply a filter...".
- Under "Pass/Fail Criteria", if a value > 0 is entered in the "min" field and the "max" field is left empty or set to "0", positive infinity is automatically re-assigned to "max".
- Peak labels in the figure window are now formatted as "Pn" (e.g., P1) and are displayed next to the peak and base markers. ([#75](https://github.com/imreburn/Wavelength-Reference/issues/75))
- Many labels and names were changed for consistency and readability.

### Fixed

- Fixed a bug where the refresh rate in the power readout window was slower than 20 Hz before the first run. ([#73](https://github.com/imreburn/Wavelength-Reference/issues/73))
- Fixed a bug where pressing a key unlocked the saved state if the cursor had been in an input field before the "Save" button was pressed. ([#74](https://github.com/imreburn/Wavelength-Reference/issues/74))

## [v1.1.9] - 2026-07-13

### Added

- The program exits automatically if the laptop lid is closed for more than 30 seconds or the program is left idle more than 30 minutes. ([#55](https://github.com/imreburn/Wavelength-Reference/issues/55))

### Changed

- When unchecking markers from the list "Show markers/table", the visibility is set as `legendonly` instead of 'off'.

## [v1.1.8] - 2026-07-10

### Added

- "Plot in Watt..." button has been added to the top bar of the figure window. A new window pops up when clicking the button, plotting all spectra in Watt. ([#58](https://github.com/imreburn/Wavelength-Reference/issues/58))
- A straight line is drawn between each pair of Delta markers. The mouse cursor can be snapped to this line so that users can place another Delta marker along it. **Caution:** Placing distant markers may affect performance, as these lines — containing points spaced by the step size — are not downsampled. ([#63](https://github.com/imreburn/Wavelength-Reference/issues/63))
- "Peak table" checkbox has been added under the "Show markers/table" label on the right sidebar. Unchecking it hides the peak table and pass/fail criteria message if they exist.

### Changed

- The power unit of the saved raw data changes from dBm (or dB) to **Watt**. ([#58](https://github.com/imreburn/Wavelength-Reference/issues/58))
- If the fields of "Pass/Fail Criteria" are left empty, 0 is assigned instead of showing an error message. ([#64](https://github.com/imreburn/Wavelength-Reference/issues/64))
- The delta marker table is placed first below the spectrum. ([#69](https://github.com/imreburn/Wavelength-Reference/issues/69))
- The newest marker is shown first in the delta marker table.
- The custom peak table is shown only if the Bandwidth marker exists.
- The custom peak table is shown right side of the delta marker table.
- When a Bandwidth marker is placed, the (x, y) position is shown with the marker. The width is also shown next to the offset marker.
- A title is displayed above each table.
- The overall layout is tighter.  

### Fixed

- Fixed stale values persisting after a custom peak is saved or cancelled in the "Save peak info..." modal and then changed; previously the old values remained until the user reselected another peak and the custom peak again. ([#66](https://github.com/imreburn/Wavelength-Reference/issues/66))
- Fixed an issue where some errors shown in the console were not recorded in the log file. ([#67](https://github.com/imreburn/Wavelength-Reference/issues/67))

## [v1.1.7] - 2026-07-07

### Added

- Keyboard shortcut (`p`) for "Read Power(p)..." button. ([#61](https://github.com/imreburn/Wavelength-Reference/issues/61))
- "Save peak info" window shows the wavelength, depth and width of the selected peak and insertion loss.([#57](https://github.com/imreburn/Wavelength-Reference/issues/57))

### Changed

- The name of y-axis changes to "Power (dBm or dB)", and "(dBm)" or "(dB)" is appended to the legend of each spectrum.([#56](https://github.com/imreburn/Wavelength-Reference/issues/56))

### Fixed

- The range setting for the power meter cannot be lower than -70 dBm, but the program allowed this. Now the config window gives an error message.
- Prevent an error when the power meter readout rarely gives a saturated value or fails to read.
- Fixed a bug ([#62](https://github.com/imreburn/Wavelength-Reference/issues/62))
- Fixed a bug ([#23](https://github.com/imreburn/Wavelength-Reference/issues/23)) by disabling the mouse right button.

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
