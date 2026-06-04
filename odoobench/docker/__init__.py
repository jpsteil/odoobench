"""Docker Export module for OdooBench.

Creates self-contained, portable tar.gz archives that include everything
needed to run `docker compose up` and get a working Odoo dev/test instance.
"""

from .exporter import DockerExporter
from .neutralize_sql import get_neutralize_sql

__all__ = ['DockerExporter', 'get_neutralize_sql']
