import tkinter as tk
from tkinter import scrolledtext
import sys
import threading
import matplotlib.pyplot as plt


class OutputWindow:
    def __init__(self, title="Output"):
        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry("500x400")

        self.text = scrolledtext.ScrolledText(self.root, state="disabled", wrap="word")
        self.text.pack(fill="both", expand=True, padx=10, pady=10)

        self._original_stdout = sys.stdout
        sys.stdout = self

    def write(self, msg):
        self.text.config(state="normal")
        self.text.insert("end", msg)
        self.text.see("end")
        self.text.config(state="disabled")
        self.root.update_idletasks()

    def flush(self):
        pass

    def _restore_stdout(self):
        sys.stdout = self._original_stdout

    def run_with(self, func, *args, **kwargs):
        """Run func(*args, **kwargs) in a background thread, show output, block until done.
        plt.show() calls inside func are deferred to the main thread after this window closes."""
        _original_show = plt.show
        plt.show = lambda *a, **kw: None  # suppress in thread; called for real below

        def target():
            try:
                func(*args, **kwargs)
            except Exception as e:
                self.write(f"\nError: {e}\n")

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        self.root.mainloop()
        self._restore_stdout()
        plt.show = _original_show
        plt.show()  # now on the main thread, safe to display


if __name__ == "__main__":
    def demo():
        import time
        for i in range(5):
            print(f"Step {i + 1}")
            time.sleep(0.5)
        print("Done.")

    win = OutputWindow()
    win.run_with(demo)
