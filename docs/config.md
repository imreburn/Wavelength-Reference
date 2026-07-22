## Config window

### Preset

- The program attempts to read `preset.csv` from the **path** written in `data_dir.txt` on startup.
- Once parameters are **saved** (in that, they passed checks), **Manage Presets...** button is activated. A new window pops-up, and users can replace an existing preset with the currently saved parameters, or create a new preset with them, or delete an existing preset.

---

### Multiple input channels

- Users can select input channels by selecting checkboxes. At least one must be selected.
- Data analysis is performed for the data from the least channel number only.

---

### The averaging time and the step size

- The averaging time is calculated from the step size divided by the sweep speed.
- The step size may be automatically adjusted to ensure that the averaging time is an integer and between 25 µs and 10 s.
- Leaving the step size empty or 0 is adjusted to the smallest possible step size given the sweep speed.

---

### Power meter readout

- After parameters are **saved**, the button **Read Power...** becomes active. The keyboard shortcut is **p**. A new pop-up appears, and the current powers for all four channels are read and shown in two units(dBm and W). The power is measured at the rate of 20 Hz.
- The maximum power reached while the window is open is shown in the last column.
- Power range setting is automatically adjusted by the power meter.
- The saved parameters(**TLS Power (dBm), Stop Wavelength (nm)**) are used to operate the instruments.

---

### Dynamic scan

- Users can run multiple scans with different power range settings. Up to 3 scans can be run with a decrement. For example, 10 dBm initial power meter range, 3 dynamic range scans, 10 dB decrement will lead to the first scan with 10 dBm range, the second with 0, the last with -10. The minimum power meter range is -70 dBm. An error message will be shown if the range lower than -70 is necessary for the given parameters. 

---

### Setting a reference

- Once a measurement is taken without a reference, the data can be set a reference for subsequent measurements, by clicking **Set Reference**. Then the reference is set and the button label changes to **Unset Reference**. Clicking it unloads the reference. Note that **Unset Reference** does not **replace** the existing reference. Data collected while a reference is set **cannot** be set as a reference.
- Because the parameters must be same for both reference and subsequent measurements, clicking **Change** button is assumed that the user would change parameters. Thus clicking **Change** immediately invalidates the existing reference and the last measurement cannot be set as a reference.

#### Status messages regarding reference

- **Not Set / Not Available**: There is no data available for a reference, and thus a reference is not set. This message is shown when the program is just launched or the user clicks the "Change" button. The "Set Reference" button is disabled.
- **Not Set / Available**: Measured data is available, but it is not loaded as a reference.
- **Set**: Currently, data is set a reference.

--- 

### Pass/Fail Criteria

- Users can enter a range (min, max) for peak wavelength, depth, and width.
- They are saved together with other parameters in a preset.
- All fields are 0 by default. Setting all as 0 turns off the criteria. The result is not examined, and no message is shown.
- If a wavelength range is not set but either the depth or width range is set, the test always fails.
- If a depth range is not set, it is skipped. The same applies to the width.