"""
Odoo Instance Connection Manager for OdooBench
Manages unified Odoo instance connections (SSH + Odoo config in one)
"""

import os
import sys
import sqlite3
import base64
from pathlib import Path
from typing import Optional, List, Dict, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def _get_default_db_path() -> Path:
    """
    Get the default database path based on installation mode.

    - Dev mode (PYTHONPATH or editable install): ~/.config/odoobench-dev/
    - Installed mode (pip/pipx): ~/.config/odoobench/
    """
    # Check if we're running in dev mode
    # Dev mode indicators:
    # 1. PYTHONPATH is set and contains the source directory
    # 2. Running from a directory containing setup.py/pyproject.toml
    is_dev = False

    # Check if we're running from source (editable install or PYTHONPATH)
    package_dir = Path(__file__).parent.parent
    if (package_dir / 'setup.py').exists() or (package_dir.parent / 'pyproject.toml').exists():
        # We're in the source tree
        is_dev = True

    # Also check PYTHONPATH
    pythonpath = os.environ.get('PYTHONPATH', '')
    if pythonpath and str(package_dir.parent) in pythonpath:
        is_dev = True

    # Use XDG config directory
    config_home = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))

    if is_dev:
        config_dir = Path(config_home) / 'odoobench-dev'
    else:
        config_dir = Path(config_home) / 'odoobench'

    # Ensure directory exists
    config_dir.mkdir(parents=True, exist_ok=True)

    return config_dir / 'connections.db'


class OdooInstanceManager:
    """
    Manage Odoo instance connections.

    Each connection represents one Odoo instance and includes:
    - SSH connection details (or localhost)
    - Odoo configuration (paths to odoo.conf, logs, filestore)
    - Database connection details (parsed from odoo.conf or manual)
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = _get_default_db_path()
        self.db_path = str(db_path)
        self.cipher_suite = self._get_cipher()
        self._init_db()

    def _get_cipher(self) -> Fernet:
        """Create encryption cipher using machine-specific key"""
        machine_id = str(os.getuid()) + os.path.expanduser("~")
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"odoo_backup_salt_v1",
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(machine_id.encode()))
        return Fernet(key)

    def _encrypt(self, value: str) -> Optional[str]:
        """Encrypt a string value"""
        if not value:
            return None
        return self.cipher_suite.encrypt(value.encode()).decode()

    def _decrypt(self, value: str) -> Optional[str]:
        """Decrypt an encrypted string value"""
        if not value:
            return None
        try:
            return self.cipher_suite.decrypt(value.encode()).decode()
        except Exception:
            return None

    def _init_db(self):
        """Initialize the database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create unified odoo_instances table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS odoo_instances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,

                -- SSH/Connection details
                host TEXT NOT NULL DEFAULT 'localhost',
                ssh_port INTEGER DEFAULT 22,
                ssh_username TEXT,
                ssh_password TEXT,
                ssh_key_path TEXT,
                is_local BOOLEAN DEFAULT 0,

                -- Odoo paths (auto-discovered or manual)
                odoo_conf_path TEXT,
                log_path TEXT,
                filestore_path TEXT,
                addons_path TEXT,

                -- Database connection (from odoo.conf or manual override)
                db_host TEXT DEFAULT 'localhost',
                db_port INTEGER DEFAULT 5432,
                db_user TEXT DEFAULT 'odoo',
                db_password TEXT,
                db_name TEXT,

                -- Metadata
                is_production BOOLEAN DEFAULT 0,
                allow_restore BOOLEAN DEFAULT 0,
                group_name TEXT,
                notes TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create index for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_odoo_instances_group
            ON odoo_instances(group_name)
        """)

        # Create settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create operation_logs table for backup/restore history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS operation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id INTEGER,
                operation_type TEXT NOT NULL,
                status TEXT NOT NULL,
                backup_file TEXT,
                log_text TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (instance_id) REFERENCES odoo_instances(id) ON DELETE CASCADE
            )
        """)

        # Create index for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_operation_logs_instance
            ON operation_logs(instance_id, started_at DESC)
        """)

        conn.commit()
        conn.close()

    def get_setting(self, key: str, default: str = None) -> str:
        """Get a setting value"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else default

    def set_setting(self, key: str, value: str) -> None:
        """Set a setting value"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (key, value)
        )
        conn.commit()
        conn.close()

    def save_instance(self, name: str, config: Dict[str, Any]) -> int:
        """
        Save an Odoo instance connection.

        Args:
            name: Unique name for this instance
            config: Dictionary with instance configuration

        Returns:
            The ID of the saved instance
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Encrypt passwords
        ssh_password = self._encrypt(config.get('ssh_password'))
        db_password = self._encrypt(config.get('db_password'))

        try:
            cursor.execute("""
                INSERT INTO odoo_instances (
                    name, host, ssh_port, ssh_username, ssh_password, ssh_key_path,
                    is_local, odoo_conf_path, log_path, filestore_path, addons_path,
                    db_host, db_port, db_user, db_password, db_name,
                    is_production, allow_restore, group_name, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name,
                config.get('host', 'localhost'),
                config.get('ssh_port', 22),
                config.get('ssh_username'),
                ssh_password,
                config.get('ssh_key_path'),
                config.get('is_local', False),
                config.get('odoo_conf_path'),
                config.get('log_path'),
                config.get('filestore_path'),
                config.get('addons_path'),
                config.get('db_host', 'localhost'),
                config.get('db_port', 5432),
                config.get('db_user', 'odoo'),
                db_password,
                config.get('db_name'),
                config.get('is_production', False),
                config.get('allow_restore', False),
                config.get('group_name'),
                config.get('notes'),
            ))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def update_instance(self, instance_id: int, name: str, config: Dict[str, Any]) -> bool:
        """
        Update an existing Odoo instance connection.

        Args:
            instance_id: ID of the instance to update
            name: New name for the instance
            config: Updated configuration

        Returns:
            True if successful
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Encrypt passwords
        ssh_password = self._encrypt(config.get('ssh_password'))
        db_password = self._encrypt(config.get('db_password'))

        try:
            cursor.execute("""
                UPDATE odoo_instances SET
                    name = ?, host = ?, ssh_port = ?, ssh_username = ?,
                    ssh_password = ?, ssh_key_path = ?, is_local = ?,
                    odoo_conf_path = ?, log_path = ?, filestore_path = ?,
                    addons_path = ?, db_host = ?, db_port = ?, db_user = ?,
                    db_password = ?, db_name = ?, is_production = ?,
                    allow_restore = ?, group_name = ?, notes = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                name,
                config.get('host', 'localhost'),
                config.get('ssh_port', 22),
                config.get('ssh_username'),
                ssh_password,
                config.get('ssh_key_path'),
                config.get('is_local', False),
                config.get('odoo_conf_path'),
                config.get('log_path'),
                config.get('filestore_path'),
                config.get('addons_path'),
                config.get('db_host', 'localhost'),
                config.get('db_port', 5432),
                config.get('db_user', 'odoo'),
                db_password,
                config.get('db_name'),
                config.get('is_production', False),
                config.get('allow_restore', False),
                config.get('group_name'),
                config.get('notes'),
                instance_id,
            ))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_instance(self, instance_id: int) -> Optional[Dict[str, Any]]:
        """
        Get an Odoo instance by ID.

        Returns:
            Dictionary with instance configuration, or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM odoo_instances WHERE id = ?", (instance_id,))
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        return self._row_to_dict(row)

    def get_instance_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get an Odoo instance by name.

        Returns:
            Dictionary with instance configuration, or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM odoo_instances WHERE name = ?", (name,))
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        return self._row_to_dict(row)

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a database row to a dictionary with decrypted passwords"""
        return {
            'id': row['id'],
            'name': row['name'],

            # SSH details
            'host': row['host'],
            'ssh_port': row['ssh_port'],
            'ssh_username': row['ssh_username'],
            'ssh_password': self._decrypt(row['ssh_password']),
            'ssh_key_path': row['ssh_key_path'],
            'is_local': bool(row['is_local']),

            # Odoo paths
            'odoo_conf_path': row['odoo_conf_path'],
            'log_path': row['log_path'],
            'filestore_path': row['filestore_path'],
            'addons_path': row['addons_path'],

            # Database
            'db_host': row['db_host'],
            'db_port': row['db_port'],
            'db_user': row['db_user'],
            'db_password': self._decrypt(row['db_password']),
            'db_name': row['db_name'],

            # Metadata
            'is_production': bool(row['is_production']),
            'allow_restore': bool(row['allow_restore']),
            'group_name': row['group_name'],
            'notes': row['notes'],

            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
        }

    def list_instances(self) -> List[Dict[str, Any]]:
        """
        List all Odoo instances (summary info only, no passwords).

        Returns:
            List of instance summaries
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, name, host, is_local, db_name, is_production,
                   allow_restore, group_name
            FROM odoo_instances
            ORDER BY group_name, name
        """)
        rows = cursor.fetchall()
        conn.close()

        return [
            {
                'id': row['id'],
                'name': row['name'],
                'host': row['host'],
                'is_local': bool(row['is_local']),
                'db_name': row['db_name'],
                'is_production': bool(row['is_production']),
                'allow_restore': bool(row['allow_restore']),
                'group_name': row['group_name'],
            }
            for row in rows
        ]

    def list_instances_by_group(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        List all instances organized by group.

        Returns:
            Dictionary with group names as keys and lists of instances as values
        """
        instances = self.list_instances()
        groups: Dict[str, List[Dict[str, Any]]] = {}

        for instance in instances:
            group = instance.get('group_name') or 'Ungrouped'
            if group not in groups:
                groups[group] = []
            groups[group].append(instance)

        return groups

    def delete_instance(self, instance_id: int) -> bool:
        """
        Delete an Odoo instance.

        Returns:
            True if successful
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM odoo_instances WHERE id = ?", (instance_id,))
        conn.commit()
        affected = cursor.rowcount > 0
        conn.close()

        return affected

    def get_groups(self) -> List[str]:
        """Get list of all group names"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT group_name FROM odoo_instances
            WHERE group_name IS NOT NULL AND group_name != ''
            ORDER BY group_name
        """)
        groups = [row[0] for row in cursor.fetchall()]
        conn.close()

        return groups

    def get_executor_config(self, instance_id: int) -> Optional[Dict[str, Any]]:
        """
        Get configuration suitable for creating a ConnectionExecutor.

        Returns:
            Dictionary with executor configuration
        """
        instance = self.get_instance(instance_id)
        if instance is None:
            return None

        if instance['is_local']:
            return {'is_local': True}

        return {
            'host': instance['host'],
            'port': instance['ssh_port'],
            'username': instance['ssh_username'],
            'password': instance['ssh_password'],
            'key_path': instance['ssh_key_path'],
        }

    def get_ssh_connection(self, instance_id: int) -> Optional[Dict[str, Any]]:
        """
        Get SSH connection details for an instance.
        Used by backup/restore for remote filestore operations.

        Returns:
            Dictionary with SSH connection details or None
        """
        instance = self.get_instance(instance_id)
        if instance is None:
            return None

        if instance['is_local']:
            return None  # Local connections don't need SSH

        return {
            'host': instance['host'],
            'port': instance['ssh_port'],
            'username': instance['ssh_username'],
            'password': instance['ssh_password'],
            'key_path': instance['ssh_key_path'],
        }

    def save_operation_log(self, instance_id: int, operation_type: str, status: str,
                           log_text: str, backup_file: str = None) -> int:
        """
        Save an operation log entry.

        Args:
            instance_id: ID of the connection (can be None for operations involving multiple)
            operation_type: 'backup', 'restore', or 'backup_restore'
            status: 'success', 'failed', or 'in_progress'
            log_text: Full log output
            backup_file: Path to backup file (if applicable)

        Returns:
            The ID of the log entry
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO operation_logs (instance_id, operation_type, status, backup_file, log_text, completed_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (instance_id, operation_type, status, backup_file, log_text))

        log_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return log_id

    def get_operation_logs(self, instance_id: int = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get operation logs, optionally filtered by instance.

        Args:
            instance_id: Filter by instance (None for all)
            limit: Maximum number of logs to return

        Returns:
            List of log entries
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if instance_id:
            cursor.execute("""
                SELECT ol.*, oi.name as instance_name
                FROM operation_logs ol
                LEFT JOIN odoo_instances oi ON ol.instance_id = oi.id
                WHERE ol.instance_id = ?
                ORDER BY ol.started_at DESC
                LIMIT ?
            """, (instance_id, limit))
        else:
            cursor.execute("""
                SELECT ol.*, oi.name as instance_name
                FROM operation_logs ol
                LEFT JOIN odoo_instances oi ON ol.instance_id = oi.id
                ORDER BY ol.started_at DESC
                LIMIT ?
            """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_operation_log(self, log_id: int) -> Optional[Dict[str, Any]]:
        """Get a single operation log by ID"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT ol.*, oi.name as instance_name
            FROM operation_logs ol
            LEFT JOIN odoo_instances oi ON ol.instance_id = oi.id
            WHERE ol.id = ?
        """, (log_id,))

        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    def export_instances(self) -> str:
        """Export all instances as JSON (without passwords)"""
        import json

        instances = self.list_instances()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        export_data = {
            'version': '2.0',
            'instances': []
        }

        for summary in instances:
            cursor.execute("SELECT * FROM odoo_instances WHERE id = ?", (summary['id'],))
            row = cursor.fetchone()
            if row:
                export_data['instances'].append({
                    'name': row['name'],
                    'host': row['host'],
                    'ssh_port': row['ssh_port'],
                    'ssh_username': row['ssh_username'],
                    'ssh_key_path': row['ssh_key_path'],
                    'is_local': bool(row['is_local']),
                    'odoo_conf_path': row['odoo_conf_path'],
                    'log_path': row['log_path'],
                    'filestore_path': row['filestore_path'],
                    'addons_path': row['addons_path'],
                    'db_host': row['db_host'],
                    'db_port': row['db_port'],
                    'db_user': row['db_user'],
                    'db_name': row['db_name'],
                    'is_production': bool(row['is_production']),
                    'allow_restore': bool(row['allow_restore']),
                    'group_name': row['group_name'],
                    'notes': row['notes'],
                })

        conn.close()
        return json.dumps(export_data, indent=2)

    def import_instances(self, json_data: str) -> tuple:
        """
        Import instances from JSON.

        Returns:
            Tuple of (success_count, error_count, messages)
        """
        import json

        try:
            data = json.loads(json_data)
        except json.JSONDecodeError as e:
            return 0, 1, [f"Invalid JSON: {e}"]

        success_count = 0
        error_count = 0
        messages = []

        for instance in data.get('instances', []):
            try:
                # Remove passwords (not exported)
                config = {
                    'host': instance.get('host', 'localhost'),
                    'ssh_port': instance.get('ssh_port', 22),
                    'ssh_username': instance.get('ssh_username'),
                    'ssh_key_path': instance.get('ssh_key_path'),
                    'is_local': instance.get('is_local', False),
                    'odoo_conf_path': instance.get('odoo_conf_path'),
                    'log_path': instance.get('log_path'),
                    'filestore_path': instance.get('filestore_path'),
                    'addons_path': instance.get('addons_path'),
                    'db_host': instance.get('db_host', 'localhost'),
                    'db_port': instance.get('db_port', 5432),
                    'db_user': instance.get('db_user', 'odoo'),
                    'db_name': instance.get('db_name'),
                    'is_production': instance.get('is_production', False),
                    'allow_restore': instance.get('allow_restore', False),
                    'group_name': instance.get('group_name'),
                    'notes': instance.get('notes'),
                }
                self.save_instance(instance['name'], config)
                success_count += 1
                messages.append(f"Imported: {instance['name']}")
            except sqlite3.IntegrityError:
                error_count += 1
                messages.append(f"Skipped (exists): {instance.get('name', 'unknown')}")
            except Exception as e:
                error_count += 1
                messages.append(f"Error: {instance.get('name', 'unknown')}: {e}")

        return success_count, error_count, messages
