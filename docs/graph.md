#### Analyzing measurement

**Detecting Peak(s)**

- Simple peak analysis (depth, FWHM) is included.

**Plotting**

- The default plotting backend is **Plotly** (`matplotlib` is dropped since the version 20260527).

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
- Users can build a custom peak using a bandwidth marker as a peak and the last delta maker as a base.
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

- If multiple peaks fall within the wavelength range, the peak with the deepest depth is chosen for examination.
- If the wavelength range finds a peak, the row is highlighted in blue in the peak table. It is also automatically selected in the peak list in "Save peak info...".

### Run the same test repeatedly

- To run another test with the same parameters, just click **Run(or press Enter)**.
- To do this even faster, users can click **Repeat(or press Enter)** in **the graph window**. It automates closing the graph window and clicking the "Run" button on the config window.