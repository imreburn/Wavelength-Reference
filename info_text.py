"""Help text for the ⓘ icons in the configuration window.

Each text appears in its popup exactly as written: line breaks are kept, and
lines wrap on their own after about 80 characters. Leave a blank line between
paragraphs. Leading and trailing blank lines are dropped.

Wrap text in **double asterisks** to show it in bold; the asterisks aren't
shown. A line that starts with "- " is a bullet: the popup shows "•" in place
of the "-", and the bullet's wrapped lines line up under its text.
"""

PASSFAIL_INFO = """
After each sweep, the program automatically detects peaks in the absorption spectrum. If the pass/fail test is on, one peak is checked against the wavelength, depth, and width ranges you set. The result is shown in the graph window.

**How it works**

- Set a min and max for the peak wavelength, depth, and width.

- All fields are 0 by default. An empty field counts as 0.

- If you enter a min and leave the max at 0, the max is set to infinity. The field then shows "inf".

- The wavelength range selects which peak to test. If more than one peak falls inside it, the deepest one is used. If no peak falls inside it, the test fails.

- Depth and width are checked on that peak. To skip either check, leave both its min and max at 0.

- Each peak has three depths and widths, one for each base: max, min, and avg. The pass/fail test uses the max base (Depth_max and FWHM_max in the peak table).

- A wavelength range of 0 to 0 selects no peak. So if depth or width is set without a wavelength range, the test always fails.

- When every field is 0, the test is off.

- The criteria are saved with the other parameters in a preset.
"""

REFERENCE_INFO="""
**Setting a reference**

- The most recent measurement taken without a reference can be used as the reference for later measurements. Click "Set Reference" to use it.

- Once the reference is set, the button changes to "Unset Reference". Clicking it unloads the reference but doesn't delete it. Click "Set Reference" to load it again.

- The reference and later measurements must use the same parameters. So clicking "Change" is taken to mean the parameters are about to change, and it deletes the reference right away. Then a new measurement should be taken to set a reference.

**Status messages**

- **Not Set / Not Available:** No data is available to use as a reference. This appears right after the program starts and after "Change" is clicked. The "Set Reference" button is disabled.

- **Not Set / Available:** Measured data is available but isn't set as the reference. Click "Set Reference" to set it.

- **Set:** A reference is set.
"""

PARAMETERS_INFO="""
**Step Size and Averaging Time**

- The averaging time is the step size divided by the sweep speed.

- The step size may be adjusted automatically so that the averaging time is a whole number of microseconds, between 25 µs and 10 s.

- If the step size is empty or 0, it's set to the smallest step the sweep speed allows (sweep speed × 25 µs).

- If the step size is adjusted, the field shows the new value in orange.


**Wavelength Padding (pm)**

- Extra range added before the start wavelength and after the stop wavelength. The laser actually sweeps from (start - padding) to (stop + padding). The result is trimmed to the range from start to stop.

- With the N7778C, the default is 50 pm, the same as in Keysight IL software. Keysight IL doesn't let you change it, but here you can set it from 0 to 50 pm in 10 pm steps.

- With any other source, padding is fixed at 0 and the field is disabled.
"""
