"""
Odoo Order Sync Module

Syncs sales orders and related records from a production Odoo instance
to a replica instance using OdooRPC.
"""

from .engine import SyncEngine

__all__ = ['SyncEngine']
