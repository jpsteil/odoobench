#!/usr/bin/env python3
"""
GUI launcher for OdooBench
"""

import sys


def main():
    """Launch the GUI interface"""
    try:
        import tkinter as tk
        from .gui.instance_window import InstanceWindow

        # Set className for proper window manager integration (Linux/X11)
        # This makes the app icon show correctly in GNOME overview
        root = tk.Tk(className="odoobench")
        app = InstanceWindow(root)
        root.mainloop()

    except ImportError as e:
        print("Error: GUI dependencies not available.")
        print("Please install tkinter:")
        print("  Ubuntu/Debian: sudo apt-get install python3-tk")
        print("  RHEL/CentOS/Fedora: sudo dnf install python3-tkinter")
        print("  macOS: tkinter should be included with Python")
        print(f"\nError details: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error launching GUI: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
