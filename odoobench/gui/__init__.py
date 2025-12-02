"""GUI module for OdooBench"""

try:
    from .main_window import OdooBenchGUI

    __all__ = ["OdooBenchGUI"]
except ImportError:
    # GUI not available (tkinter not installed)
    __all__ = []
