"""Help text for the ⓘ icons in the configuration window.

Each text appears in its popup exactly as written: line breaks are kept, and
lines wrap on their own after about 80 characters. Leave a blank line between
paragraphs. Leading and trailing blank lines are dropped.

Wrap text in **double asterisks** to show it in bold; the asterisks aren't
shown. A line that starts with "- " is a bullet: the popup shows "•" in place
of the "-", and the bullet's wrapped lines line up under its text.
"""

PARAMETERS_INFO="""
**Step Size and Averaging Time**

- Averaging Time = (Step Size / Sweep Speed)

- The step size may be adjusted automatically so that the averaging time is a whole number of microseconds, between 25 µs and 10 s.

- If the step size is empty or 0, it's set to the smallest step the sweep speed allows (sweep speed × 25 µs).

- If the step size is adjusted, the field shows the new value in orange.


**Wavelength Padding (pm)**

- Extra range added before the start wavelength and after the stop wavelength. The laser actually sweeps from (start - padding) to (stop + padding). The result is trimmed to the range from start to stop.

- With the N7778C, the default is 50 pm, the same as in Keysight IL software. Keysight IL doesn't let you change it, but here you can set it from 0 to 50 pm in 10 pm steps.

- With any other source, padding is fixed at 0 and the field is disabled.
"""


REFERENCE_INFO="""
**Using a reference**

- The most recent measurement taken without a reference can be used as the reference for later measurements. Check "Use reference" to use it.

- Unchecking "Use reference" stops using the reference but doesn't delete it. Check the box again to use it again. A new measurement taken while the box is unchecked replaces it.

- The reference and later measurements must use the same parameters. So clicking "Change" is taken to mean the parameters are about to change, and it deletes the reference right away. Then a new measurement should be taken before a reference can be used.


**Status messages**

- **No data:** No data is available to use as a reference. This appears right after the program starts and after "Change" is clicked. The "Use reference" checkbox is disabled.

- **Data ready:** Measured data is available but isn't being used as the reference. Check "Use reference" to use it.

- **In use:** The reference is in use.
"""


PASSFAIL_INFO = """
After each sweep, the program automatically detects peaks in the absorption spectrum. If the pass/fail test is on, one peak is checked against the wavelength, depth, and width ranges you set. The result is shown in the graph window.


**Depth and width**

Each peak has two base points, one on each side (left and right). Depth and width (FWHM) are measured from a base level, and this program calculates them three ways:

- max: the base with the higher power, which gives the largest depth.
- min: the base with the lower power, which gives the smallest depth. This is the standard peak prominence, as in SciPy.
- avg: the average of the two bases.

The pass/fail test uses **max** (Depth_max and FWHM_max in the peak table).


**Setting the criteria**

- Set a min and max for the peak wavelength, depth, and width.

- All fields are 0 by default. An empty field counts as 0.

- If you enter a min and leave the max at 0, the max is set to infinity. The field then shows "inf".

- To skip the depth or width check, leave both its min and max at 0.

- When every field is 0, the test is off.

- Like the other parameters, the criteria lock when you click Save and are stored in presets.


**How a peak is tested**

- The wavelength range selects which peak to test. If more than one peak falls inside it, the one with the largest Depth_max is used. If no peak falls inside it, the test fails.

- Depth and width are then checked on that peak.

- A wavelength range of 0 to 0 selects no peak. So if depth or width is set without a wavelength range, the test always fails.
"""


AUTOSAVE_INFO="""
The fields in this section don't lock after Save, so you can change them without clicking Change. They aren't saved in presets and are kept until the program closes.


**Label**

- Check "Add label (SN)" to give each sweep a label: a prefix followed by a counter. For example, in SN007, SN is the prefix and 007 is the counter. The label is previewed next to the checkbox.

- You can leave out either the prefix or the counter, but not both. The prefix can be any text, even just numbers, but it can't contain \\ / : * ? " < > | or end with a space or a dot, because the label can become part of a file name.

- The counter is set with two fields: "Digits" and "Starting from". "Digits" (0 to 4) sets how many digits the counter has, and 0 means no counter. The counter is padded with zeros, so 3 digits starting from 7 gives 007.

- "Digits" also sets the range for "Starting from". With 2 digits, for example, you can enter 0 to 99.

- **The counter automatically increases by 1 after each sweep finishes. Numbers in the prefix never change.** After a cancelled or failed sweep, the counter stays the same, so you can try again with the same label. Once the last value is used (99 with 2 digits), the window shows an error, and Run won't start until you change "Digits" or "Starting from".

- The label is shown above the top-left corner of the plot in the graph window. It also fills in the "Label / Serial number" field in the "Save peak info" window.


**Auto-save raw data**

- If "Auto-save raw data" is checked, the raw data is saved to the Raw Data folder after each sweep. The file is the same as the one "Save raw data..." saves in the graph window.

- The graph window shows a status message with the file name, or an error if the save failed.

- With a label, the file name is "<label>_<time>.csv". Without one, it's "<time>.csv". The time is when you click Run, in the form YYYY-MM-DD_hh-mm-ss. The name is previewed next to the checkbox.
"""
