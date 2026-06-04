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

                -- Odoo web login (for OdooRPC sync)
                odoo_user TEXT,
                odoo_password TEXT,

                -- PostgreSQL server SSH (for running pg_dump on PG server)
                -- If empty, falls back to Odoo server SSH credentials
                pg_ssh_host TEXT,
                pg_ssh_port INTEGER,
                pg_ssh_username TEXT,
                pg_ssh_password TEXT,
                pg_ssh_key_path TEXT,

                -- Metadata
                is_production BOOLEAN DEFAULT 0,
                allow_restore BOOLEAN DEFAULT 0,
                allow_sync BOOLEAN DEFAULT 0,
                group_name TEXT,
                notes TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration: Add pg_ssh_* columns if they don't exist
        cursor.execute("PRAGMA table_info(odoo_instances)")
        columns = [row[1] for row in cursor.fetchall()]
        for col in ['pg_ssh_host', 'pg_ssh_port', 'pg_ssh_username', 'pg_ssh_password', 'pg_ssh_key_path']:
            if col not in columns:
                col_type = "INTEGER" if col == 'pg_ssh_port' else "TEXT"
                cursor.execute(f"ALTER TABLE odoo_instances ADD COLUMN {col} {col_type}")

        # Migration: Add allow_sync column if it doesn't exist
        if 'allow_sync' not in columns:
            cursor.execute("ALTER TABLE odoo_instances ADD COLUMN allow_sync BOOLEAN DEFAULT 0")

        # Migration: Add Odoo web login columns if they don't exist
        for col in ['odoo_user', 'odoo_password']:
            if col not in columns:
                cursor.execute(f"ALTER TABLE odoo_instances ADD COLUMN {col} TEXT")

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

        # Create docker_export_profiles table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS docker_export_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                odoo_instance_id INTEGER REFERENCES odoo_instances(id) ON DELETE CASCADE,
                source_base_dir TEXT,
                source_subdirs TEXT,
                venv_path TEXT,
                extra_files TEXT,
                odoo_conf_path TEXT,
                container_base_dir TEXT DEFAULT '/opt/odoo/qlf',
                postgres_version TEXT DEFAULT '16',
                python_version TEXT DEFAULT '3.12',
                odoo_port INTEGER DEFAULT 8069,
                mailpit_http_port INTEGER DEFAULT 8025,
                custom_neutralize_sql TEXT,
                git_repo_url TEXT,
                git_clone_subdir TEXT,
                output_dir TEXT,
                include_db INTEGER DEFAULT 1,
                include_filestore INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration: Add include_db and include_filestore columns if they don't exist
        cursor.execute("PRAGMA table_info(docker_export_profiles)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'include_db' not in columns:
            cursor.execute("ALTER TABLE docker_export_profiles ADD COLUMN include_db INTEGER DEFAULT 1")
        if 'include_filestore' not in columns:
            cursor.execute("ALTER TABLE docker_export_profiles ADD COLUMN include_filestore INTEGER DEFAULT 1")

        # Create index for docker export profiles
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_docker_export_profiles_instance
            ON docker_export_profiles(odoo_instance_id)
        """)

        # Create sync_transactions table for tracking synced records
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT NOT NULL,
                source_instance_id INTEGER NOT NULL,
                source_id INTEGER NOT NULL,
                target_instance_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                source_write_date TEXT,
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_instance_id) REFERENCES odoo_instances(id) ON DELETE CASCADE,
                FOREIGN KEY (target_instance_id) REFERENCES odoo_instances(id) ON DELETE CASCADE,
                UNIQUE(model, source_instance_id, source_id, target_instance_id)
            )
        """)

        # Create indexes for sync_transactions
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sync_lookup
            ON sync_transactions(model, source_instance_id, source_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sync_target
            ON sync_transactions(model, target_instance_id, target_id)
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
        odoo_password = self._encrypt(config.get('odoo_password'))
        pg_ssh_password = self._encrypt(config.get('pg_ssh_password'))

        try:
            cursor.execute("""
                INSERT INTO odoo_instances (
                    name, host, ssh_port, ssh_username, ssh_password, ssh_key_path,
                    is_local, odoo_conf_path, log_path, filestore_path, addons_path,
                    db_host, db_port, db_user, db_password, db_name,
                    odoo_user, odoo_password,
                    pg_ssh_host, pg_ssh_port, pg_ssh_username, pg_ssh_password, pg_ssh_key_path,
                    is_production, allow_restore, allow_sync, group_name, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                config.get('odoo_user'),
                odoo_password,
                config.get('pg_ssh_host'),
                config.get('pg_ssh_port'),
                config.get('pg_ssh_username'),
                pg_ssh_password,
                config.get('pg_ssh_key_path'),
                config.get('is_production', False),
                config.get('allow_restore', False),
                config.get('allow_sync', False),
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
        odoo_password = self._encrypt(config.get('odoo_password'))
        pg_ssh_password = self._encrypt(config.get('pg_ssh_password'))

        try:
            cursor.execute("""
                UPDATE odoo_instances SET
                    name = ?, host = ?, ssh_port = ?, ssh_username = ?,
                    ssh_password = ?, ssh_key_path = ?, is_local = ?,
                    odoo_conf_path = ?, log_path = ?, filestore_path = ?,
                    addons_path = ?, db_host = ?, db_port = ?, db_user = ?,
                    db_password = ?, db_name = ?,
                    odoo_user = ?, odoo_password = ?,
                    pg_ssh_host = ?, pg_ssh_port = ?, pg_ssh_username = ?,
                    pg_ssh_password = ?, pg_ssh_key_path = ?,
                    is_production = ?, allow_restore = ?, allow_sync = ?,
                    group_name = ?, notes = ?,
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
                config.get('odoo_user'),
                odoo_password,
                config.get('pg_ssh_host'),
                config.get('pg_ssh_port'),
                config.get('pg_ssh_username'),
                pg_ssh_password,
                config.get('pg_ssh_key_path'),
                config.get('is_production', False),
                config.get('allow_restore', False),
                config.get('allow_sync', False),
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

            # Odoo web login
            'odoo_user': row['odoo_user'] if 'odoo_user' in row.keys() else None,
            'odoo_password': self._decrypt(row['odoo_password']) if 'odoo_password' in row.keys() and row['odoo_password'] else None,

            # PostgreSQL server SSH
            'pg_ssh_host': row['pg_ssh_host'],
            'pg_ssh_port': row['pg_ssh_port'],
            'pg_ssh_username': row['pg_ssh_username'],
            'pg_ssh_password': self._decrypt(row['pg_ssh_password']),
            'pg_ssh_key_path': row['pg_ssh_key_path'],

            # Metadata
            'is_production': bool(row['is_production']),
            'allow_restore': bool(row['allow_restore']),
            'allow_sync': bool(row['allow_sync']) if row['allow_sync'] is not None else False,
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
                   allow_restore, allow_sync, group_name
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
                'allow_sync': bool(row['allow_sync']) if row['allow_sync'] is not None else False,
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

    # =================================================================
    # Docker Export Profile Methods
    # =================================================================

    def save_docker_export_profile(self, name: str, config: Dict[str, Any]) -> int:
        """
        Save a Docker export profile.

        Args:
            name: Unique name for this profile
            config: Profile configuration dict

        Returns:
            The ID of the saved profile
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO docker_export_profiles (
                    name, odoo_instance_id, source_base_dir, source_subdirs,
                    venv_path, extra_files, odoo_conf_path, container_base_dir,
                    postgres_version, python_version, odoo_port, mailpit_http_port,
                    custom_neutralize_sql, git_repo_url, git_clone_subdir, output_dir,
                    include_db, include_filestore
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name,
                config.get('odoo_instance_id'),
                config.get('source_base_dir'),
                config.get('source_subdirs', '[]'),
                config.get('venv_path'),
                config.get('extra_files', '[]'),
                config.get('odoo_conf_path'),
                config.get('container_base_dir', '/opt/odoo/qlf'),
                config.get('postgres_version', '16'),
                config.get('python_version', '3.12'),
                config.get('odoo_port', 8069),
                config.get('mailpit_http_port', 8025),
                config.get('custom_neutralize_sql'),
                config.get('git_repo_url'),
                config.get('git_clone_subdir'),
                config.get('output_dir'),
                config.get('include_db', 1),
                config.get('include_filestore', 1),
            ))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def update_docker_export_profile(self, profile_id: int, name: str, config: Dict[str, Any]) -> bool:
        """
        Update an existing Docker export profile.

        Args:
            profile_id: ID of the profile to update
            name: New name for the profile
            config: Updated configuration

        Returns:
            True if successful
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE docker_export_profiles SET
                    name = ?, odoo_instance_id = ?, source_base_dir = ?,
                    source_subdirs = ?, venv_path = ?, extra_files = ?,
                    odoo_conf_path = ?, container_base_dir = ?, postgres_version = ?,
                    python_version = ?, odoo_port = ?, mailpit_http_port = ?,
                    custom_neutralize_sql = ?, git_repo_url = ?, git_clone_subdir = ?,
                    output_dir = ?, include_db = ?, include_filestore = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                name,
                config.get('odoo_instance_id'),
                config.get('source_base_dir'),
                config.get('source_subdirs', '[]'),
                config.get('venv_path'),
                config.get('extra_files', '[]'),
                config.get('odoo_conf_path'),
                config.get('container_base_dir', '/opt/odoo/qlf'),
                config.get('postgres_version', '16'),
                config.get('python_version', '3.12'),
                config.get('odoo_port', 8069),
                config.get('mailpit_http_port', 8025),
                config.get('custom_neutralize_sql'),
                config.get('git_repo_url'),
                config.get('git_clone_subdir'),
                config.get('output_dir'),
                config.get('include_db', 1),
                config.get('include_filestore', 1),
                profile_id,
            ))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_docker_export_profile(self, profile_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a Docker export profile by ID.

        Returns:
            Dictionary with profile configuration, or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM docker_export_profiles WHERE id = ?", (profile_id,))
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        return dict(row)

    def get_docker_export_profile_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get a Docker export profile by name.

        Returns:
            Dictionary with profile configuration, or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM docker_export_profiles WHERE name = ?", (name,))
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        return dict(row)

    def list_docker_export_profiles(self, odoo_instance_id: int = None) -> List[Dict[str, Any]]:
        """
        List Docker export profiles, optionally filtered by instance.

        Args:
            odoo_instance_id: Filter by instance (None for all)

        Returns:
            List of profile summaries
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if odoo_instance_id:
            cursor.execute("""
                SELECT dep.*, oi.name as instance_name
                FROM docker_export_profiles dep
                LEFT JOIN odoo_instances oi ON dep.odoo_instance_id = oi.id
                WHERE dep.odoo_instance_id = ?
                ORDER BY dep.name
            """, (odoo_instance_id,))
        else:
            cursor.execute("""
                SELECT dep.*, oi.name as instance_name
                FROM docker_export_profiles dep
                LEFT JOIN odoo_instances oi ON dep.odoo_instance_id = oi.id
                ORDER BY dep.name
            """)

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def delete_docker_export_profile(self, profile_id: int) -> bool:
        """
        Delete a Docker export profile.

        Returns:
            True if successful
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM docker_export_profiles WHERE id = ?", (profile_id,))
        conn.commit()
        affected = cursor.rowcount > 0
        conn.close()

        return affected

    # =================================================================
    # Sync Transaction Methods
    # =================================================================

    def get_sync_mapping(self, model: str, source_instance_id: int,
                          source_id: int, target_instance_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a sync mapping for a specific record.

        Args:
            model: Model name (e.g., 'sale.order')
            source_instance_id: Source instance ID
            source_id: Source record ID
            target_instance_id: Target instance ID

        Returns:
            Dictionary with mapping info, or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM sync_transactions
            WHERE model = ? AND source_instance_id = ?
            AND source_id = ? AND target_instance_id = ?
        """, (model, source_instance_id, source_id, target_instance_id))

        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    def save_sync_mapping(self, model: str, source_instance_id: int,
                           source_id: int, target_instance_id: int,
                           target_id: int, source_write_date: str = None) -> int:
        """
        Save or update a sync mapping.

        Args:
            model: Model name (e.g., 'sale.order')
            source_instance_id: Source instance ID
            source_id: Source record ID
            target_instance_id: Target instance ID
            target_id: Target record ID
            source_write_date: Source record write_date

        Returns:
            The ID of the mapping
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO sync_transactions
            (model, source_instance_id, source_id, target_instance_id, target_id,
             source_write_date, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(model, source_instance_id, source_id, target_instance_id)
            DO UPDATE SET
                target_id = excluded.target_id,
                source_write_date = excluded.source_write_date,
                synced_at = CURRENT_TIMESTAMP
        """, (model, source_instance_id, source_id, target_instance_id,
              target_id, source_write_date))

        conn.commit()
        mapping_id = cursor.lastrowid
        conn.close()

        return mapping_id

    def get_synced_source_ids(self, model: str, source_instance_id: int,
                               target_instance_id: int) -> List[int]:
        """
        Get all source IDs that have been synced for a model.

        Args:
            model: Model name
            source_instance_id: Source instance ID
            target_instance_id: Target instance ID

        Returns:
            List of source IDs
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT source_id FROM sync_transactions
            WHERE model = ? AND source_instance_id = ?
            AND target_instance_id = ?
        """, (model, source_instance_id, target_instance_id))

        ids = [row[0] for row in cursor.fetchall()]
        conn.close()

        return ids

    def get_last_sync_time(self, model: str, source_instance_id: int,
                            target_instance_id: int) -> Optional[str]:
        """
        Get the most recent source_write_date for a model sync.

        Args:
            model: Model name
            source_instance_id: Source instance ID
            target_instance_id: Target instance ID

        Returns:
            The most recent source_write_date, or None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT MAX(source_write_date) FROM sync_transactions
            WHERE model = ? AND source_instance_id = ?
            AND target_instance_id = ?
        """, (model, source_instance_id, target_instance_id))

        result = cursor.fetchone()
        conn.close()

        return result[0] if result and result[0] else None

    def delete_sync_mapping(self, model: str, source_instance_id: int,
                             source_id: int, target_instance_id: int) -> bool:
        """
        Delete a sync mapping.

        Args:
            model: Model name
            source_instance_id: Source instance ID
            source_id: Source record ID
            target_instance_id: Target instance ID

        Returns:
            True if deleted
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM sync_transactions
            WHERE model = ? AND source_instance_id = ?
            AND source_id = ? AND target_instance_id = ?
        """, (model, source_instance_id, source_id, target_instance_id))

        conn.commit()
        affected = cursor.rowcount > 0
        conn.close()

        return affected

    def delete_sync_mappings_for_instance(self, source_instance_id: int = None,
                                           target_instance_id: int = None) -> int:
        """
        Delete all sync mappings for an instance (source or target).

        Args:
            source_instance_id: Delete mappings where this is the source
            target_instance_id: Delete mappings where this is the target

        Returns:
            Number of deleted mappings
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        conditions = []
        params = []

        if source_instance_id:
            conditions.append("source_instance_id = ?")
            params.append(source_instance_id)
        if target_instance_id:
            conditions.append("target_instance_id = ?")
            params.append(target_instance_id)

        if not conditions:
            conn.close()
            return 0

        query = f"DELETE FROM sync_transactions WHERE {' OR '.join(conditions)}"
        cursor.execute(query, params)

        conn.commit()
        affected = cursor.rowcount
        conn.close()

        return affected

    def get_sync_stats(self, source_instance_id: int,
                        target_instance_id: int) -> Dict[str, int]:
        """
        Get sync statistics for a source/target pair.

        Returns:
            Dictionary with model names as keys and record counts as values
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT model, COUNT(*) as count
            FROM sync_transactions
            WHERE source_instance_id = ? AND target_instance_id = ?
            GROUP BY model
        """, (source_instance_id, target_instance_id))

        stats = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()

        return stats
