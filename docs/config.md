#### Load/Save/Delete Preset

- The program attempts to read `preset.csv` from the path written in `datapath.txt` on startup.
- Once parameters are **saved** (in that, they passed checks), **Manage Presets...** button is activated. In the pop-up, users can replace an existing preset with the currently saved parameters, create a new preset with them, or delete an existing preset.

---

#### Read Power in real-time

- Once parameters are **saved**, **Read Power...** becomes active. In the pop-up, the current powers for all four channels are read and shown in two units(dBm and W), and updated at the rate of 20 Hz.
- Power range setting is automatically adjusted by the power meter.
- Parameters for source power and wavelength are referred from the saved parameters: **TLS Power (dBm), Stop Wavelength (nm)**, respectively.

---

#### Setting a Reference

- Once a measurement is taken, it can be set a reference for subsequent measurements, by clicking **Set Reference**. The reference is set and the button changes to **Unset Reference**. Users can unset the reference by clicking it.
- Because the parameters must be same for both reference and subsequent measurements, clicking **Change** button is assumed that the user would change parameters. Thus clicking **Change** immediately invalidates the existing reference and the last measurement cannot be set as a reference.

#### Multiple input channels

- Users can select input channels by selecting checkboxes up to 4. At least one must be selected.

#### Pass/Fail Criteria

- Users can enter a range (min, max) for peak wavelength, depth, and width.
- They are saved together with other parameters in a preset.
- All fields are 0 by default. Setting all as 0 turns off the criteria. The result is not examined, and no message is shown.
- If a wavelength range is not set but either the depth or width range is set, the test always fails.
- If a depth range is not set, it is skipped. The same applies to the width.