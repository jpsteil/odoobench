"""
Odoo Configuration Parser for OdooBench
Parses odoo.conf files and discovers Odoo instance settings
"""

import configparser
import os
from typing import Dict, Any, Optional
from .executor import ConnectionExecutor


class OdooConfigParser:
    """Parse odoo.conf files to extract configuration"""

    # Common odoo.conf locations to try
    DEFAULT_CONF_PATHS = [
        '/etc/odoo/odoo.conf',
        '/etc/odoo-server.conf',
        '/etc/odoo.conf',
        '/opt/odoo/odoo.conf',
        '~/.odoorc',
        '~/.openerp_serverrc',
    ]

    # Default log paths to check
    DEFAULT_LOG_PATHS = [
        '/var/log/odoo/odoo-server.log',
        '/var/log/odoo/odoo.log',
        '/var/log/odoo-server.log',
        '/opt/odoo/odoo.log',
    ]

    def __init__(self, executor: ConnectionExecutor):
        """
        Initialize parser with a connection executor

        Args:
            executor: ConnectionExecutor for local or SSH access
        """
        self.executor = executor

    def find_odoo_conf(self) -> Optional[str]:
        """
        Try to find odoo.conf on the system

        Returns:
            Path to odoo.conf if found, None otherwise
        """
        for path in self.DEFAULT_CONF_PATHS:
            expanded = os.path.expanduser(path)
            if self.executor.file_exists(expanded):
                return expanded
        return None

    def find_log_file(self, conf_path: Optional[str] = None) -> Optional[str]:
        """
        Find the Odoo log file

        Args:
            conf_path: Optional path to odoo.conf (will parse for logfile setting)

        Returns:
            Path to log file if found
        """
        # First try to get from config
        if conf_path:
            try:
                config = self.parse_config(conf_path)
                if config.get('log_path'):
                    return config['log_path']
            except:
                pass

        # Fall back to default locations
        for path in self.DEFAULT_LOG_PATHS:
            if self.executor.file_exists(path):
                return path

        return None

    def parse_config(self, conf_path: str) -> Dict[str, Any]:
        """
        Parse an odoo.conf file and extract settings

        Args:
            conf_path: Path to odoo.conf

        Returns:
            Dictionary with extracted configuration
        """
        # Read the config file
        content = self.executor.read_file(conf_path)

        # Parse with configparser
        config = configparser.ConfigParser()
        config.read_string(content)

        result = {
            'odoo_conf_path': conf_path,
        }

        # Get the options section
        if 'options' not in config:
            return result

        options = config['options']

        # Database connection
        result['db_host'] = options.get('db_host', 'localhost')
        result['db_port'] = int(options.get('db_port', 5432))
        result['db_user'] = options.get('db_user', 'odoo')
        result['db_password'] = self._clean_value(options.get('db_password', ''))
        result['db_name'] = self._clean_value(options.get('db_name', ''))

        # Paths
        result['filestore_path'] = self._clean_value(options.get('data_dir', ''))
        result['log_path'] = self._clean_value(options.get('logfile', ''))
        result['addons_path'] = self._clean_value(options.get('addons_path', ''))

        # Server settings (useful for health checks)
        result['http_port'] = int(options.get('http_port', options.get('xmlrpc_port', 8069)))
        result['workers'] = int(options.get('workers', 0))

        # Try to determine Odoo version from addons path
        result['odoo_version'] = self._detect_version(result.get('addons_path', ''))

        return result

    def _clean_value(self, value: str) -> str:
        """Clean up a config value (handle False, None, empty)"""
        if not value or value.lower() in ('false', 'none', ''):
            return ''
        return value.strip()

    def _detect_version(self, addons_path: str) -> str:
        """Try to detect Odoo version from addons path"""
        if not addons_path:
            return ''

        # Look for version patterns in path
        version_patterns = ['18.0', '17.0', '16.0', '15.0', '14.0', '13.0', '12.0']
        for version in version_patterns:
            if version in addons_path:
                return version

        return ''

    def discover_all(self, conf_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Discover all Odoo configuration, auto-detecting where possible

        Args:
            conf_path: Optional explicit path to odoo.conf

        Returns:
            Complete configuration dictionary
        """
        result = {}

        # Find or use provided conf path
        if conf_path:
            if not self.executor.file_exists(conf_path):
                raise FileNotFoundError(f"Config file not found: {conf_path}")
            result['odoo_conf_path'] = conf_path
        else:
            found_conf = self.find_odoo_conf()
            if found_conf:
                result['odoo_conf_path'] = found_conf

        # Parse config if found
        if result.get('odoo_conf_path'):
            parsed = self.parse_config(result['odoo_conf_path'])
            result.update(parsed)

        # Find log file if not in config
        if not result.get('log_path'):
            log_path = self.find_log_file()
            if log_path:
                result['log_path'] = log_path

        # Set default filestore if not found
        if not result.get('filestore_path'):
            # Try to detect the user's home directory for proper path construction
            stdout, stderr, code = self.executor.run_command("echo $HOME")
            user_home = stdout.strip() if code == 0 and stdout.strip() else os.path.expanduser("~")

            default_paths = [
                '/var/lib/odoo',
                f'{user_home}/.local/share/Odoo',
                '/opt/odoo/.local/share/Odoo',
            ]
            for path in default_paths:
                if self.executor.dir_exists(path):
                    result['filestore_path'] = path
                    break

        return result

    def get_databases(self, db_host: str = 'localhost', db_port: int = 5432,
                      db_user: str = 'odoo', db_password: str = '') -> list:
        """
        List available databases on the PostgreSQL server

        Args:
            db_host: Database host
            db_port: Database port
            db_user: Database username
            db_password: Database password

        Returns:
            List of database names
        """
        # Build psql command to list databases
        env_prefix = f"PGPASSWORD='{db_password}' " if db_password else ""
        cmd = f"{env_prefix}psql -h {db_host} -p {db_port} -U {db_user} -d postgres -t -c \"SELECT datname FROM pg_database WHERE datistemplate = false AND datname NOT IN ('postgres') ORDER BY datname;\""

        stdout, stderr, code = self.executor.run_command(cmd)

        if code != 0:
            return []

        # Parse output
        databases = [db.strip() for db in stdout.strip().split('\n') if db.strip()]
        return databases

    def test_database_connection(self, db_host: str = 'localhost', db_port: int = 5432,
                                  db_user: str = 'odoo', db_password: str = '') -> tuple:
        """
        Test database connection

        Returns:
            Tuple of (success: bool, message: str)
        """
        env_prefix = f"PGPASSWORD='{db_password}' " if db_password else ""
        cmd = f"{env_prefix}psql -h {db_host} -p {db_port} -U {db_user} -d postgres -c \"SELECT version();\" 2>&1"

        stdout, stderr, code = self.executor.run_command(cmd, timeout=10)

        if code == 0:
            return True, "Database connection successful"
        else:
            error = stderr or stdout
            return False, f"Connection failed: {error}"

    def get_odoo_service_status(self) -> tuple:
        """
        Check if Odoo service is running

        Returns:
            Tuple of (running: bool, message: str)
        """
        # Try systemd first
        stdout, stderr, code = self.executor.run_command(
            "systemctl is-active odoo 2>/dev/null || systemctl is-active odoo-server 2>/dev/null"
        )

        if code == 0 and stdout.strip() == 'active':
            return True, "Odoo service is running"

        # Try checking for process
        stdout, stderr, code = self.executor.run_command(
            "pgrep -f 'odoo.*http' > /dev/null && echo 'running' || echo 'stopped'"
        )

        if 'running' in stdout:
            return True, "Odoo process is running"

        return False, "Odoo is not running"

    def get_disk_usage(self, path: str) -> Dict[str, Any]:
        """
        Get disk usage for a path

        Returns:
            Dictionary with total, used, available in bytes and percentage
        """
        stdout, stderr, code = self.executor.run_command(f"df -B1 '{path}' | tail -1")

        if code != 0:
            return {}

        parts = stdout.split()
        if len(parts) >= 5:
            return {
                'total': int(parts[1]),
                'used': int(parts[2]),
                'available': int(parts[3]),
                'percent_used': parts[4].rstrip('%'),
            }

        return {}
