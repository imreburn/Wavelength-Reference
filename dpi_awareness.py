"""Process-wide Windows DPI awareness for the tkinter GUIs.

Without declaring DPI awareness, Windows draws a tkinter window at logical
96 DPI and then bitmap-stretches the result up to the monitor's actual scaling
(125/150%). Stretching a finished bitmap is what makes text and 1px lines look
blurry until a later redraw forces native re-rendering.

DPI awareness is a process-wide setting that can only be applied *before the
first window is created*, so this module performs the call as an import-time
side effect: any module that needs crisp tkinter rendering simply does
``import dpi_awareness`` at the top, before its first ``tk.Tk()``. Python caches
modules, so the call runs exactly once per process no matter how many files
import it. No-op off Windows.
"""
import sys
import logging

log = logging.getLogger(__name__)


def enable_windows_dpi_awareness():
    if not sys.platform.startswith("win"):
        return
    try:
        from ctypes import windll
        # PROCESS_PER_MONITOR_DPI_AWARE (2); fall back to system-DPI-aware
        # (SetProcessDPIAware) on older Windows that lacks shcore.
        try:
            windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            windll.user32.SetProcessDPIAware()
    except Exception as exc:  # never let DPI setup break the GUI
        log.debug("Could not set DPI awareness: %s", exc)


enable_windows_dpi_awareness()
