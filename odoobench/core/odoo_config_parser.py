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
        psql, use_local = self._find_psql()
        env_prefix = f"PGPASSWORD='{db_password}' " if db_password else ""
        cmd = f"{env_prefix}{psql} -h {db_host} -p {db_port} -U {db_user} -d postgres -t -c \"SELECT datname FROM pg_database WHERE datistemplate = false AND datname NOT IN ('postgres') ORDER BY datname;\""

        stdout, stderr, code = self._run_psql_command(cmd, use_local)

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
        psql, use_local = self._find_psql()
        env_prefix = f"PGPASSWORD='{db_password}' " if db_password else ""
        cmd = f"{env_prefix}{psql} -h {db_host} -p {db_port} -U {db_user} -d postgres -c \"SELECT version();\" 2>&1"

        stdout, stderr, code = self._run_psql_command(cmd, use_local)

        if code == 0:
            return True, f"Database connection successful{' (using local psql)' if use_local else ''}"
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

    def _find_psql(self) -> tuple:
        """
        Find the psql command, checking common paths.

        Returns:
            Tuple of (psql_path, use_local) where use_local indicates
            whether to run psql locally instead of via the executor.
        """
        # Try common PostgreSQL paths first (most reliable)
        common_paths = [
            '/usr/bin/psql',
            '/usr/local/bin/psql',
            '/usr/pgsql-17/bin/psql',
            '/usr/pgsql-16/bin/psql',
            '/usr/pgsql-15/bin/psql',
            '/usr/pgsql-14/bin/psql',
            '/usr/lib/postgresql/17/bin/psql',
            '/usr/lib/postgresql/16/bin/psql',
            '/usr/lib/postgresql/15/bin/psql',
            '/usr/lib/postgresql/14/bin/psql',
            '/opt/postgresql/bin/psql',
        ]

        for path in common_paths:
            stdout, stderr, code = self.executor.run_command(f"[ -x {path} ] && echo yes")
            if code == 0 and 'yes' in stdout:
                return (path, False)

        # Try 'which psql'
        stdout, stderr, code = self.executor.run_command("which psql 2>/dev/null")
        if code == 0 and stdout.strip() and '/' in stdout:
            return (stdout.strip(), False)

        # Try command -v (more portable than which)
        stdout, stderr, code = self.executor.run_command("command -v psql 2>/dev/null")
        if code == 0 and stdout.strip() and '/' in stdout:
            return (stdout.strip(), False)

        # psql not found on remote - try locally instead
        import subprocess
        try:
            result = subprocess.run(['which', 'psql'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return (result.stdout.strip(), True)  # Use local psql
        except Exception:
            pass

        # Fall back to just 'psql' on remote and hope it's in PATH
        return ('psql', False)

    def _run_psql_command(self, cmd: str, use_local: bool = False) -> tuple:
        """Run a psql command either locally or via executor."""
        if use_local:
            import subprocess
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=30
                )
                return (result.stdout, result.stderr, result.returncode)
            except subprocess.TimeoutExpired:
                return ("", "Command timed out", -1)
            except Exception as e:
                return ("", str(e), -1)
        else:
            return self.executor.run_command(cmd)

    def get_postgresql_settings(self, db_host: str = 'localhost', db_port: int = 5432,
                                 db_user: str = 'odoo', db_password: str = '',
                                 db_name: str = 'postgres') -> Dict[str, Any]:
        """
        Get PostgreSQL configuration settings relevant for Odoo performance

        Returns:
            Dictionary with setting names, values, and units
        """
        psql, use_local = self._find_psql()

        settings_query = """
        SELECT name, setting, unit, boot_val, context
        FROM pg_settings
        WHERE name IN (
            'shared_buffers', 'effective_cache_size', 'work_mem',
            'maintenance_work_mem', 'max_connections', 'random_page_cost',
            'effective_io_concurrency', 'checkpoint_completion_target',
            'wal_buffers', 'max_parallel_workers_per_gather',
            'max_worker_processes', 'max_parallel_workers'
        )
        ORDER BY name;
        """

        env_prefix = f"PGPASSWORD='{db_password}' " if db_password else ""
        cmd = f"{env_prefix}{psql} -h {db_host} -p {db_port} -U {db_user} -d {db_name} -t -A -F '|' -c \"{settings_query}\""

        stdout, stderr, code = self._run_psql_command(cmd, use_local)

        if code != 0:
            error_msg = stderr or stdout
            if 'command not found' in error_msg or 'not found' in error_msg:
                return {'error': "psql not found. Install postgresql-client on either:\n"
                                 "  - The Odoo server (SSH target), or\n"
                                 "  - Your local machine running OdooBench"}
            return {'error': error_msg}

        settings = {}
        for line in stdout.strip().split('\n'):
            if '|' in line:
                parts = line.split('|')
                if len(parts) >= 3:
                    name = parts[0]
                    value = parts[1]
                    unit = parts[2] if parts[2] else ''
                    settings[name] = {
                        'value': value,
                        'unit': unit,
                        'boot_val': parts[3] if len(parts) > 3 else '',
                        'context': parts[4] if len(parts) > 4 else '',
                    }

        return settings

    def get_server_memory(self, db_host: str = 'localhost', db_port: int = 5432,
                          db_user: str = 'odoo', db_password: str = '',
                          db_name: str = 'postgres') -> Optional[int]:
        """
        Get total server memory in bytes (for calculating recommendations)

        Returns:
            Total memory in bytes, or None if unable to determine
        """
        # Try to get from PostgreSQL (works on Linux)
        query = "SELECT pg_size_pretty(setting::bigint * 1024) FROM pg_settings WHERE name = 'shared_buffers';"

        # First try to read /proc/meminfo via psql shell command
        env_prefix = f"PGPASSWORD='{db_password}' " if db_password else ""
        cmd = f"{env_prefix}psql -h {db_host} -p {db_port} -U {db_user} -d {db_name} -t -c \"COPY (SELECT 1) TO PROGRAM 'cat /proc/meminfo | grep MemTotal'\" 2>/dev/null || echo ''"

        # Simpler approach - just run on the host
        stdout, stderr, code = self.executor.run_command("grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}'")

        if code == 0 and stdout.strip():
            try:
                return int(stdout.strip()) * 1024  # Convert KB to bytes
            except ValueError:
                pass

        return None

    def get_database_stats(self, db_host: str = 'localhost', db_port: int = 5432,
                           db_user: str = 'odoo', db_password: str = '',
                           db_name: str = 'postgres') -> Dict[str, Any]:
        """
        Get database health statistics

        Returns:
            Dictionary with database stats including size, connections, cache hit ratio
        """
        psql, use_local = self._find_psql()
        stats_query = """
        SELECT
            pg_database_size(current_database()) as db_size,
            (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()) as active_connections,
            (SELECT count(*) FROM pg_stat_activity) as total_connections,
            (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') as max_connections;
        """

        env_prefix = f"PGPASSWORD='{db_password}' " if db_password else ""
        db_to_query = db_name if db_name and db_name != 'postgres' else 'postgres'
        cmd = f"{env_prefix}{psql} -h {db_host} -p {db_port} -U {db_user} -d {db_to_query} -t -A -F '|' -c \"{stats_query}\""

        stdout, stderr, code = self._run_psql_command(cmd, use_local)

        stats = {}
        if code == 0 and stdout.strip():
            parts = stdout.strip().split('|')
            if len(parts) >= 4:
                stats['db_size'] = int(parts[0]) if parts[0] else 0
                stats['active_connections'] = int(parts[1]) if parts[1] else 0
                stats['total_connections'] = int(parts[2]) if parts[2] else 0
                stats['max_connections'] = int(parts[3]) if parts[3] else 0

        # Get cache hit ratio
        cache_query = """
        SELECT
            CASE WHEN (blks_hit + blks_read) > 0
                THEN round(100.0 * blks_hit / (blks_hit + blks_read), 2)
                ELSE 0
            END as cache_hit_ratio
        FROM pg_stat_database
        WHERE datname = current_database();
        """
        cmd = f"{env_prefix}{psql} -h {db_host} -p {db_port} -U {db_user} -d {db_to_query} -t -c \"{cache_query}\""
        stdout, stderr, code = self._run_psql_command(cmd, use_local)
        if code == 0 and stdout.strip():
            try:
                stats['cache_hit_ratio'] = float(stdout.strip())
            except ValueError:
                stats['cache_hit_ratio'] = 0

        # Get table bloat info (simplified - count of tables needing vacuum)
        bloat_query = """
        SELECT count(*)
        FROM pg_stat_user_tables
        WHERE n_dead_tup > 10000;
        """
        cmd = f"{env_prefix}{psql} -h {db_host} -p {db_port} -U {db_user} -d {db_to_query} -t -c \"{bloat_query}\""
        stdout, stderr, code = self._run_psql_command(cmd, use_local)
        if code == 0 and stdout.strip():
            try:
                stats['tables_needing_vacuum'] = int(stdout.strip())
            except ValueError:
                stats['tables_needing_vacuum'] = 0

        # Get last vacuum times for critical tables
        vacuum_query = """
        SELECT relname, last_vacuum, last_autovacuum, last_analyze, last_autoanalyze
        FROM pg_stat_user_tables
        ORDER BY n_dead_tup DESC
        LIMIT 5;
        """
        cmd = f"{env_prefix}{psql} -h {db_host} -p {db_port} -U {db_user} -d {db_to_query} -t -A -F '|' -c \"{vacuum_query}\""
        stdout, stderr, code = self._run_psql_command(cmd, use_local)
        if code == 0 and stdout.strip():
            tables = []
            for line in stdout.strip().split('\n'):
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 5:
                        tables.append({
                            'name': parts[0],
                            'last_vacuum': parts[1] or 'Never',
                            'last_autovacuum': parts[2] or 'Never',
                            'last_analyze': parts[3] or 'Never',
                            'last_autoanalyze': parts[4] or 'Never',
                        })
            stats['top_tables'] = tables

        return stats

    def get_postgresql_version(self, db_host: str = 'localhost', db_port: int = 5432,
                                db_user: str = 'odoo', db_password: str = '') -> str:
        """Get PostgreSQL version string"""
        psql, use_local = self._find_psql()
        env_prefix = f"PGPASSWORD='{db_password}' " if db_password else ""
        cmd = f"{env_prefix}{psql} -h {db_host} -p {db_port} -U {db_user} -d postgres -t -c \"SELECT version();\""

        stdout, stderr, code = self._run_psql_command(cmd, use_local)
        if code == 0:
            return stdout.strip()
        return ""
