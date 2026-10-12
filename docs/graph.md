## Graph window

### Top Navigation Bar

#### Save Raw Data...

- Raw data can be saved as a CSV file. The user can set the location and the name of the file from the pop-up window. The default path is set as the `Raw Data` folder in the [data location](../README.md#data-location).

#### Save Peak Info...

- **P** key is the keyboard shortcut.
- Label (SN) cannot be left empty.
- I.L. and Temperature can be left empty.
- If the pass/fail criteria finds a peak, it will be automatically selected from the peak list. A note "(criteria)" is added to the peak.
- The peak with the maximum depth (based on 'Depth_max') is noted "(max depth)", and will be listed next to the one found by the criteria. The same peak may be chosen by both conditions.

#### Show / Hide...

- **H** key is the keyboard shortcut.
- Shows or hides what's drawn on and under the plot: the peaks and their left and right bases, the Peak table, the width markers, the Pass/Fail table, and the insertion loss marker.
- "All" and each "(all)" box tick or clear their whole group.
- A hidden plot item stays in the legend. Clicking it there shows it again.

#### Analyzing measurement

**Detecting Peak(s)**

- Simple peak analysis (depth, FWHM) is included.

**Plotting**

- The default plotting backend is **Plotly** (`matplotlib` is dropped since the version 20260527).
- Press **X** to reset the zoom. It does the same as the "Autoscale" or "Reset axes" button in the plot's toolbar.

---

#### Saving Results to CSV

Users can save raw data and peak data to CSV files.

**Save Raw Data**

- Parameters are saved in the first line.
- Raw data includes wavelength (nm) and power (dBm) values for each input channel.
- Reference data is saved together.
- For multiple dynamic scans, only the combined spectrum is saved.

**Save Peak Info**

- Keyboard shortcut: **p**
- Label (SN) cannot be left empty.
- I.L. and Temperature can be left empty.
- Users can build a custom peak with the two Bandwidth markers: B1 is the peak and B2 is the base. In Bandwidth click mode, the first click places B1 and the second places B2. After that, clicks take turns moving them: the third click moves B1, the fourth moves B2, and so on. "Clear all" starts over from B1.
- If the pass/fail criteria finds a peak, it will be automatically selected from the peak list. A note "(criteria)" is added to the peak.
- The peak with the maximum depth (based on 'Depth_max') is noted "(max depth)", and will be listed next to the one found by the criteria. The same peak may be chosen by both conditions.

---

#### Reference

- Difference between the new measurement and the reference is calculated element-by-element. The minimum is taken as the insertion loss. The difference spectra is shown as the main spectra.
- The unmodified reference and new measurement spectra will be drawn but invisible at start. Users can click legends to make them visible.

---

#### More than one input channel

- Peak analysis is performed only for a single channel with the least channel number.

---

### Pass/Fail Criteria

- The result is shown in a table titled "Pass/Fail test result", just above the Peak table. It lists each criterion's range, the tested peak's measured value, and the result of each check. The overall result, "Pass" in green or "Fail" in red, is in the last column. The "Criteria [min, max]" row shows each range's min and max, and both ends count as inside. "∞" means no upper limit, and "—" means the check isn't set. "Customize..." next to the title sets how many decimal places the measured values show.
- If multiple peaks fall within the wavelength range, the peak with the deepest depth is chosen for examination.
- If the wavelength range finds a peak, the row is highlighted in blue in the peak table. It is also automatically selected in the peak list in "Save peak info...".

### Run the same test repeatedly

- To run another test with the same parameters, just click **Run(or press Enter)**.
- To do this even faster, users can click **Repeat(or press Enter)** in **the graph window**. It automates closing the graph window and clicking the "Run" button on the config window.