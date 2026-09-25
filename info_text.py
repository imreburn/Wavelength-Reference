"""Help text for the ⓘ icons in the configuration window.

Each text appears in its popup exactly as written: line breaks are kept, and
lines wrap on their own after about 80 characters. Leave a blank line between
paragraphs. Leading and trailing blank lines are dropped.
"""

PASSFAIL_INFO = """
- Set a min and max for the peak wavelength, depth, and width.

- All fields are 0 by default. An empty field counts as 0.

- If you enter a min and leave the max at 0, the max is set to infinity. The field then shows "inf".

- The wavelength range selects which peak to test. If more than one peak falls inside it, the deepest one is used. If no peak falls inside it, the test fails.

- Depth and width are checked on that peak. To skip either check, leave both its min and max at 0.

- A wavelength range of 0 to 0 selects no peak. So if depth or width is set without a wavelength range, the test always fails.

- When every field is 0, the test is off.

- The criteria are saved with the other parameters in a preset.
"""

REFERENCE_INFO="""
Setting a reference

- The most recent measurement taken without a reference can be used as the reference for later measurements. Click "Set Reference" to use it.

- Once the reference is set, the button changes to "Unset Reference". Clicking it unloads the reference but doesn't delete it. Click "Set Reference" to load it again.

- The reference and later measurements must use the same parameters. So clicking "Change" is considered as parameters are about to change, and it deletes the reference right away. Then a new measurement should be taken to set a reference.


Status messages

- Not Set / Not Available: No data is available to use as a reference. This appears right after the program starts and after "Change" is clicked. The "Set Reference" button is disabled.

- Not Set / Available: Measured data is available but isn't set as the reference. Click "Set Reference" to set it.

- Set: A reference is set.
"""
