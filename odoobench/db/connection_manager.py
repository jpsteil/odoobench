"""
Connection Manager for OdooBench
Handles storage and retrieval of database and SSH connection profiles with encryption
"""

import os
import sqlite3
import base64
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class ConnectionManager:
    """Manage saved database connections with encrypted passwords"""

    def __init__(self, db_path=None):
        if db_path is None:
            # Store database inside the package directory
            db_path = Path(__file__).parent / "connections.db"
        self.db_path = str(db_path)
        self.cipher_suite = self._get_cipher()
        self._init_db()

    def _get_cipher(self):
        """Create encryption cipher using machine-specific key"""
        # Use machine ID and username for key generation
        machine_id = str(os.getuid()) + os.path.expanduser("~")
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"odoo_backup_salt_v1",
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(machine_id.encode()))
        return Fernet(key)

    def _init_db(self):
        """Initialize SQLite database with proper 3NF schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check if we need to migrate from old single-table schema
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='connections'"
        )
        old_table_exists = cursor.fetchone() is not None

        # Create SSH connections table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ssh_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL DEFAULT 22,
                username TEXT NOT NULL,
                password TEXT,
                key_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Create Odoo connections table with foreign key to SSH connections
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS odoo_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL DEFAULT 5432,
                database TEXT,
                username TEXT NOT NULL,
                password TEXT,
                filestore_path TEXT,
                odoo_version TEXT DEFAULT '17.0',
                is_local BOOLEAN DEFAULT 0,
                allow_restore BOOLEAN DEFAULT 0,
                ssh_connection_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ssh_connection_id) REFERENCES ssh_connections(id) ON DELETE SET NULL
            )
            """
        )

        # Create settings table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Migrate data from old schema if it exists
        if old_table_exists:
            self._migrate_old_schema(cursor)
            cursor.execute("DROP TABLE connections")

        conn.commit()
        conn.close()

    def _migrate_old_schema(self, cursor):
        """Migrate data from old single-table schema to new 3NF schema"""
        cursor.execute("SELECT * FROM connections")
        old_connections = cursor.fetchall()

        # Get column names for mapping
        cursor.execute("PRAGMA table_info(connections)")
        columns_info = cursor.fetchall()
        column_names = [col[1] for col in columns_info]

        for row in old_connections:
            # Create a dict for easier access
            conn_data = dict(zip(column_names, row))

            # Determine connection type
            conn_type = conn_data.get("connection_type", "odoo")

            if conn_type == "ssh":
                # Migrate SSH connection
                try:
                    cursor.execute(
                        """
                        INSERT INTO ssh_connections (name, host, port, username, password, key_path)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            conn_data.get("name"),
                            conn_data.get(
                                "host", conn_data.get("ssh_host", "localhost")
                            ),
                            conn_data.get("port", conn_data.get("ssh_port", 22)),
                            conn_data.get("username", conn_data.get("ssh_user", "")),
                            conn_data.get("password", conn_data.get("ssh_password")),
                            conn_data.get("ssh_key_path", ""),
                        ),
                    )
                except sqlite3.IntegrityError:
                    pass  # Skip duplicates
            else:
                # Migrate Odoo connection
                # First check if it references an SSH connection
                ssh_conn_id = None
                if conn_data.get("use_ssh") and conn_data.get("ssh_host"):
                    # Try to find matching SSH connection
                    cursor.execute(
                        "SELECT id FROM ssh_connections WHERE host = ? AND username = ?",
                        (conn_data.get("ssh_host"), conn_data.get("ssh_user", "")),
                    )
                    ssh_result = cursor.fetchone()
                    if ssh_result:
                        ssh_conn_id = ssh_result[0]

                try:
                    cursor.execute(
                        """
                        INSERT INTO odoo_connections
                        (name, host, port, database, username, password, filestore_path,
                         odoo_version, is_local, ssh_connection_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            conn_data.get("name"),
                            conn_data.get("host", "localhost"),
                            conn_data.get("port", 5432),
                            conn_data.get("database", ""),
                            conn_data.get("username", "odoo"),
                            conn_data.get("password"),
                            conn_data.get("filestore_path", ""),
                            conn_data.get("odoo_version", "17.0"),
                            conn_data.get("is_local", False),
                            ssh_conn_id,
                        ),
                    )
                except sqlite3.IntegrityError:
                    pass  # Skip duplicates

    def save_ssh_connection(self, name, config):
        """Save an SSH connection profile"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Encrypt password if provided
        encrypted_password = None
        if config.get("password"):
            encrypted_password = self.cipher_suite.encrypt(
                config["password"].encode()
            ).decode()

        try:
            cursor.execute(
                """
                INSERT OR REPLACE INTO ssh_connections
                (name, host, port, username, password, key_path)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    name,
                    config.get("host", "localhost"),
                    config.get("port", 22),
                    config.get("username", ""),
                    encrypted_password,
                    config.get("ssh_key_path", ""),
                ),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def save_odoo_connection(self, name, config):
        """Save an Odoo connection profile"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Encrypt password if provided
        encrypted_password = None
        if config.get("password"):
            encrypted_password = self.cipher_suite.encrypt(
                config["password"].encode()
            ).decode()

        # Get SSH connection ID if specified
        ssh_conn_id = None
        if config.get("ssh_connection_name"):
            cursor.execute(
                "SELECT id FROM ssh_connections WHERE name = ?",
                (config["ssh_connection_name"],),
            )
            result = cursor.fetchone()
            if result:
                ssh_conn_id = result[0]

        try:
            cursor.execute(
                """
                INSERT OR REPLACE INTO odoo_connections
                (name, host, port, database, username, password, filestore_path,
                 odoo_version, is_local, allow_restore, ssh_connection_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    name,
                    config.get("host", "localhost"),
                    config.get("port", 5432),
                    config.get("database", ""),
                    config.get("username", "odoo"),
                    encrypted_password,
                    config.get("filestore_path", ""),
                    config.get("odoo_version", "17.0"),
                    config.get("is_local", False),
                    config.get("allow_restore", False),  # Default to False for safety
                    ssh_conn_id,
                ),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def save_connection(self, name, config):
        """Save a connection - routes to appropriate method based on type"""
        conn_type = config.get("connection_type", "odoo")
        if conn_type == "ssh":
            return self.save_ssh_connection(name, config)
        else:
            return self.save_odoo_connection(name, config)

    def update_ssh_connection(self, conn_id, name, config):
        """Update an SSH connection by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Encrypt password if provided
        encrypted_password = None
        if config.get("password"):
            encrypted_password = self.cipher_suite.encrypt(
                config["password"].encode()
            ).decode()

        try:
            cursor.execute(
                """
                UPDATE ssh_connections
                SET name = ?, host = ?, port = ?, username = ?, password = ?, key_path = ?
                WHERE id = ?
            """,
                (
                    name,
                    config.get("host", "localhost"),
                    config.get("port", 22),
                    config.get("username", ""),
                    encrypted_password,
                    config.get("ssh_key_path", ""),
                    conn_id,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def update_odoo_connection(self, conn_id, name, config):
        """Update an Odoo connection by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Encrypt password if provided
        encrypted_password = None
        if config.get("password"):
            encrypted_password = self.cipher_suite.encrypt(
                config["password"].encode()
            ).decode()

        # SSH connection ID is passed directly now
        ssh_conn_id = config.get("ssh_connection_id")

        try:
            cursor.execute(
                """
                UPDATE odoo_connections
                SET name = ?, host = ?, port = ?, database = ?, username = ?,
                    password = ?, filestore_path = ?, odoo_version = ?,
                    is_local = ?, allow_restore = ?, ssh_connection_id = ?
                WHERE id = ?
            """,
                (
                    name,
                    config.get("host", "localhost"),
                    config.get("port", 5432),
                    config.get("database", ""),
                    config.get("username", "odoo"),
                    encrypted_password,
                    config.get("filestore_path", ""),
                    config.get("odoo_version", "17.0"),
                    config.get("is_local", False),
                    config.get("allow_restore", False),  # Default to False for safety
                    ssh_conn_id,
                    conn_id,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def get_ssh_connection(self, conn_id):
        """Get an SSH connection by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                id,         -- 0
                name,       -- 1
                host,       -- 2
                port,       -- 3
                username,   -- 4
                password,   -- 5
                key_path,   -- 6
                created_at, -- 7
                updated_at  -- 8
            FROM ssh_connections
            WHERE id = ?
            """,
            (conn_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            config = {
                "id": row[0],           # id
                "name": row[1],         # name
                "host": row[2],         # host
                "port": row[3],         # port
                "username": row[4],     # username
                "password": None,       # Will be decrypted below
                "ssh_key_path": row[6] if row[6] else "",  # key_path
                "created_at": row[7],   # created_at
                "updated_at": row[8],   # updated_at
                "connection_type": "ssh",
            }
            # Decrypt password
            if row[5]:
                try:
                    config["password"] = self.cipher_suite.decrypt(
                        row[5].encode()
                    ).decode()
                except:
                    pass
            return config
        return None

    def get_odoo_connection(self, conn_id):
        """Get an Odoo connection by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                o.id,                  -- 0
                o.name,                -- 1
                o.host,                -- 2
                o.port,                -- 3
                o.database,            -- 4
                o.username,            -- 5
                o.password,            -- 6
                o.filestore_path,      -- 7
                o.odoo_version,        -- 8
                o.is_local,            -- 9
                o.allow_restore,       -- 10
                o.ssh_connection_id,   -- 11
                o.created_at,          -- 12
                o.updated_at,          -- 13
                s.name as ssh_name,    -- 14
                s.host as ssh_host,    -- 15
                s.port as ssh_port,    -- 16
                s.username as ssh_user,-- 17
                s.password as ssh_pass,-- 18
                s.key_path             -- 19
            FROM odoo_connections o
            LEFT JOIN ssh_connections s ON o.ssh_connection_id = s.id
            WHERE o.id = ?
        """,
            (conn_id,),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            # Columns are now explicitly defined in the SELECT statement above
            config = {
                "id": row[0],                               # o.id
                "name": row[1],                             # o.name
                "host": row[2],                             # o.host
                "port": row[3],                             # o.port
                "database": row[4] if row[4] else "",       # o.database
                "username": row[5],                         # o.username
                "password": None,                           # Will be decrypted below
                "filestore_path": row[7] if row[7] else "", # o.filestore_path
                "odoo_version": row[8] if row[8] else "17.0", # o.odoo_version
                "is_local": row[9] if row[9] else False,    # o.is_local
                "allow_restore": row[10] if row[10] else False, # o.allow_restore
                "ssh_connection_id": row[11] if row[11] else None, # o.ssh_connection_id
                "created_at": row[12],                      # o.created_at
                "updated_at": row[13],                      # o.updated_at
                "use_ssh": row[11] is not None,             # Has SSH if ssh_connection_id exists
                # SSH joined columns (will be None if no SSH connection)
                "ssh_connection_name": row[14] if row[11] else "", # s.name
                "ssh_host": row[15] if row[11] else "",     # s.host
                "ssh_port": row[16] if row[11] else 22,     # s.port
                "ssh_user": row[17] if row[11] else "",     # s.username
                "ssh_password": None,                       # Will be decrypted if exists
                "ssh_key_path": row[19] if row[11] else "", # s.key_path
                "connection_type": "odoo",
            }

            # Decrypt Odoo password
            if row[6]:
                try:
                    config["password"] = self.cipher_suite.decrypt(
                        row[6].encode()
                    ).decode()
                except:
                    pass

            # Decrypt SSH password if exists
            if row[11] and len(row) > 18 and row[18]:
                try:
                    config["ssh_password"] = self.cipher_suite.decrypt(
                        row[18].encode()
                    ).decode()
                except:
                    pass

            return config
        return None

    def list_connections(self):
        """List all saved connections from both tables with IDs"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get all connections with ID, name, and type info
        all_connections = []

        # Get SSH connections
        cursor.execute(
            "SELECT id, name, host, port, username FROM ssh_connections ORDER BY name"
        )
        for row in cursor.fetchall():
            all_connections.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "host": row[2],
                    "port": row[3],
                    "username": row[4],
                    "type": "ssh",
                }
            )

        # Get Odoo connections
        cursor.execute(
            "SELECT id, name, host, port, database, username, allow_restore FROM odoo_connections ORDER BY name"
        )
        for row in cursor.fetchall():
            all_connections.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "host": row[2],
                    "port": row[3],
                    "database": row[4],
                    "username": row[5],
                    "allow_restore": row[6] if len(row) > 6 else False,
                    "type": "odoo",
                }
            )

        conn.close()
        return all_connections

    def delete_ssh_connection(self, conn_id):
        """Delete an SSH connection by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ssh_connections WHERE id = ?", (conn_id,))
        conn.commit()
        affected = cursor.rowcount > 0
        conn.close()
        return affected

    def delete_odoo_connection(self, conn_id):
        """Delete an Odoo connection by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM odoo_connections WHERE id = ?", (conn_id,))
        conn.commit()
        affected = cursor.rowcount > 0
        conn.close()
        return affected

    def get_setting(self, key, default=None):
        """Get a setting value from the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else default

    def set_setting(self, key, value):
        """Set a setting value in the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (key, value),
        )
        conn.commit()
        conn.close()

    def export_connections(self):
        """Export all connections as JSON (without passwords)."""
        import json

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        export_data = {
            "version": "1.0",
            "ssh_connections": [],
            "odoo_connections": [],
        }

        # Export SSH connections (without passwords)
        cursor.execute(
            """
            SELECT name, host, port, username, key_path
            FROM ssh_connections
            ORDER BY name
            """
        )
        for row in cursor.fetchall():
            export_data["ssh_connections"].append({
                "name": row[0],
                "host": row[1],
                "port": row[2],
                "username": row[3],
                "key_path": row[4] or "",
            })

        # Export Odoo connections (without passwords)
        cursor.execute(
            """
            SELECT o.name, o.host, o.port, o.database, o.username,
                   o.filestore_path, o.odoo_version, o.is_local, o.allow_restore,
                   s.name as ssh_name
            FROM odoo_connections o
            LEFT JOIN ssh_connections s ON o.ssh_connection_id = s.id
            ORDER BY o.name
            """
        )
        for row in cursor.fetchall():
            export_data["odoo_connections"].append({
                "name": row[0],
                "host": row[1],
                "port": row[2],
                "database": row[3] or "",
                "username": row[4],
                "filestore_path": row[5] or "",
                "odoo_version": row[6] or "17.0",
                "is_local": bool(row[7]),
                "allow_restore": bool(row[8]),
                "ssh_connection_name": row[9] or "",
            })

        conn.close()
        return json.dumps(export_data, indent=2)

    def import_connections(self, json_data):
        """Import connections from JSON. Returns (success_count, error_count, messages)."""
        import json

        try:
            data = json.loads(json_data)
        except json.JSONDecodeError as e:
            return 0, 1, [f"Invalid JSON: {e}"]

        success_count = 0
        error_count = 0
        messages = []

        # Import SSH connections first (so they can be referenced by Odoo connections)
        for ssh in data.get("ssh_connections", []):
            try:
                config = {
                    "host": ssh.get("host", "localhost"),
                    "port": ssh.get("port", 22),
                    "username": ssh.get("username", ""),
                    "password": None,  # Passwords not imported
                    "ssh_key_path": ssh.get("key_path", ""),
                }
                if self.save_ssh_connection(ssh["name"], config):
                    success_count += 1
                    messages.append(f"Imported SSH: {ssh['name']}")
                else:
                    error_count += 1
                    messages.append(f"Failed to import SSH: {ssh['name']}")
            except Exception as e:
                error_count += 1
                messages.append(f"Error importing SSH {ssh.get('name', 'unknown')}: {e}")

        # Import Odoo connections
        for odoo in data.get("odoo_connections", []):
            try:
                config = {
                    "host": odoo.get("host", "localhost"),
                    "port": odoo.get("port", 5432),
                    "database": odoo.get("database", ""),
                    "username": odoo.get("username", "odoo"),
                    "password": None,  # Passwords not imported
                    "filestore_path": odoo.get("filestore_path", ""),
                    "odoo_version": odoo.get("odoo_version", "17.0"),
                    "is_local": odoo.get("is_local", False),
                    "allow_restore": odoo.get("allow_restore", False),
                    "ssh_connection_name": odoo.get("ssh_connection_name", ""),
                }
                if self.save_odoo_connection(odoo["name"], config):
                    success_count += 1
                    messages.append(f"Imported Odoo: {odoo['name']}")
                else:
                    error_count += 1
                    messages.append(f"Failed to import Odoo: {odoo['name']}")
            except Exception as e:
                error_count += 1
                messages.append(f"Error importing Odoo {odoo.get('name', 'unknown')}: {e}")

        return success_count, error_count, messages
