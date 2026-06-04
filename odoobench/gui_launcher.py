#!/usr/bin/env python3
"""
GUI launcher for OdooBench (PyQt6)
"""

import sys


def main():
    """Launch the GUI interface"""
    try:
        from .gui_qt.main_window import launch
        launch()
    except ImportError as e:
        print("Error: PyQt6 not available.")
        print("Please install PyQt6:")
        print("  pip install PyQt6")
        print(f"\nError details: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error launching GUI: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
