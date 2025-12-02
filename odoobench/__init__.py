"""
OdooBench - A comprehensive backup and restore utility for Odoo instances
"""

from .version import __version__

__author__ = "Jim Steil"

from .core.backup_restore import OdooBench
from .db.connection_manager import ConnectionManager

__all__ = ["OdooBench", "ConnectionManager", "__version__"]
