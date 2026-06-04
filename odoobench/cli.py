#!/usr/bin/env python3
"""
Command-line interface for OdooBench
"""

import sys
import os
import argparse
import json
from pathlib import Path
import getpass


def detect_gui_capability():
    """Detect if GUI can be launched"""
    # Check for display (Linux/Unix)
    if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY') and not sys.platform.startswith('win') and not sys.platform == 'darwin':
        return False

    # Check if tkinter is available
    try:
        import tkinter
        return True
    except ImportError:
        return False


def should_launch_gui(args=None):
    """Determine if GUI should be launched based on environment and arguments"""
    # If we have args, check for explicit CLI/GUI flags
    if args:
        # Force CLI mode if --cli flag is present
        if hasattr(args, 'cli') and args.cli:
            return False
        # Force GUI mode if --gui flag is present
        if hasattr(args, 'gui') and args.gui:
            if not detect_gui_capability():
                print("Error: GUI requested but not available.")
                print("Please install tkinter: sudo apt-get install python3-tk")
                print("Or use --cli flag to force CLI mode.")
                sys.exit(1)
            return True

    # If no specific command given, default to GUI if available
    if not args or not args.command:
        return detect_gui_capability()

    # If a command was given, stay in CLI mode
    return False


def main():
    """Main entry point with smart GUI/CLI detection"""
    # First, check if any arguments were provided
    if len(sys.argv) == 1:
        # No arguments - try to launch GUI if available
        if detect_gui_capability():
            launch_gui()
            return

    # Parse arguments
    parser = create_parser()
    args = parser.parse_args()

    # Check if we should launch GUI based on args and environment
    if should_launch_gui(args):
        launch_gui()
    else:
        # Handle CLI commands
        handle_cli(parser, args)


def create_parser():
    """Create the argument parser"""
    parser = argparse.ArgumentParser(
        description="OdooBench - Odoo Database and Filestore Backup/Restore Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Default behavior:
  odoobench              # Launches GUI if available, otherwise shows help
  odoobench --cli        # Force CLI mode, shows help
  odoobench --gui        # Force GUI mode (error if not available)

Examples:
  # Save a connection profile (do this first)
  odoobench --cli connections save --name prod --host db.example.com --user odoo --database mydb --filestore /var/lib/odoo
  odoobench --cli connections save --name dev --host localhost --user odoo --database devdb --allow-restore

  # Backup using connection profile
  odoobench --cli backup --connection prod

  # Restore using connection profile
  odoobench --cli restore --connection dev --file backup.tar.gz --name test_db

  # List saved connections
  odoobench --cli connections list

  # Manual backup (without saved connection)
  odoobench --cli backup --name mydb --host localhost --user odoo --filestore /var/lib/odoo/filestore

  # Manual restore (without saved connection)
  odoobench --cli restore --file backup.tar.gz --name newdb --host localhost --user odoo
        """,
    )

    # Add mode selection flags
    parser.add_argument(
        "--cli", action="store_true",
        help="Force CLI mode (don't launch GUI even if available)"
    )
    parser.add_argument(
        "--gui", action="store_true",
        help="Force GUI mode (error if GUI not available)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Backup command
    backup_parser = subparsers.add_parser("backup", help="Create a backup")
    backup_parser.add_argument("--connection", "-c", help="Use saved connection profile (recommended)")
    backup_parser.add_argument("--name", help="Database name (required if not using connection)")
    backup_parser.add_argument("--host", default="localhost", help="Database host")
    backup_parser.add_argument("--port", type=int, default=5432, help="Database port")
    backup_parser.add_argument("--user", default="odoo", help="Database user")
    backup_parser.add_argument(
        "--password", help="Database password (will prompt if not provided)"
    )
    backup_parser.add_argument("--filestore", help="Filestore path")
    backup_parser.add_argument("--output-dir", help="Output directory for backup")
    backup_parser.add_argument(
        "--no-filestore", action="store_true", help="Skip filestore backup"
    )

    # Restore command
    restore_parser = subparsers.add_parser("restore", help="Restore from backup")
    restore_parser.add_argument("--file", "-f", required=True, help="Backup file to restore")
    restore_parser.add_argument("--connection", "-c", help="Use saved connection profile (recommended)")
    restore_parser.add_argument("--name", help="Target database name (required if not using connection)")
    restore_parser.add_argument("--host", default="localhost", help="Database host")
    restore_parser.add_argument("--port", type=int, default=5432, help="Database port")
    restore_parser.add_argument("--user", default="odoo", help="Database user")
    restore_parser.add_argument(
        "--password", help="Database password (will prompt if not provided)"
    )
    restore_parser.add_argument("--filestore", help="Target filestore path")
    restore_parser.add_argument(
        "--no-filestore", action="store_true", help="Skip filestore restore"
    )
    restore_parser.add_argument(
        "--neutralize", action="store_true",
        help="Neutralize database for testing (disable emails, crons, payment providers, etc.)"
    )

    # Connections management
    conn_parser = subparsers.add_parser("connections", help="Manage saved connections")
    conn_subparsers = conn_parser.add_subparsers(
        dest="conn_action", help="Connection actions"
    )

    # List connections
    conn_list = conn_subparsers.add_parser("list", help="List saved connections")

    # Save connection
    conn_save = conn_subparsers.add_parser("save", help="Save a new connection")
    conn_save.add_argument("--name", required=True, help="Connection name")
    conn_save.add_argument("--host", required=True, help="Database host")
    conn_save.add_argument("--port", type=int, default=5432, help="Database port")
    conn_save.add_argument("--database", help="Database name")
    conn_save.add_argument("--user", default="odoo", help="Database user")
    conn_save.add_argument("--password", help="Database password")
    conn_save.add_argument("--filestore", help="Filestore path")
    conn_save.add_argument("--odoo-version", default="17.0", help="Odoo version")
    conn_save.add_argument(
        "--allow-restore", action="store_true",
        help="Allow restore operations to this connection (use for dev/test only, not production)"
    )

    # Delete connection
    conn_delete = conn_subparsers.add_parser("delete", help="Delete a connection")
    conn_delete.add_argument("name", help="Connection name to delete")

    # Test connection
    conn_test = conn_subparsers.add_parser("test", help="Test a connection")
    conn_test.add_argument("name", help="Connection name to test")

    # Parse config file
    config_parser = subparsers.add_parser("from-config", help="Run from odoo.conf file")
    config_parser.add_argument("config_file", help="Path to odoo.conf file")
    config_parser.add_argument("--backup", action="store_true", help="Perform backup")
    config_parser.add_argument("--output-dir", help="Output directory for backup")

    # Docker export command
    docker_parser = subparsers.add_parser("docker-export", help="Create Docker package")
    docker_parser.add_argument("--connection", "-c", required=True, help="Source Odoo connection name")
    docker_parser.add_argument("--profile", "-p", help="Docker export profile name (uses saved profile)")
    docker_parser.add_argument("--output-dir", help="Output directory for the Docker archive")
    docker_parser.add_argument("--source-dir", help="Remote source directory base path")
    docker_parser.add_argument("--subdirs", help="Comma-separated list of source subdirectories")
    docker_parser.add_argument("--venv-path", help="Path to Python virtual environment")
    docker_parser.add_argument("--odoo-conf-path", help="Relative path to odoo.conf from source-dir")
    docker_parser.add_argument("--extra-files", help="Comma-separated extra files to include")
    docker_parser.add_argument("--pg-version", default="16", help="PostgreSQL version (default: 16)")
    docker_parser.add_argument("--python-version", default="3.12", help="Python version (default: 3.12)")
    docker_parser.add_argument("--odoo-port", type=int, default=8069, help="Odoo HTTP port (default: 8069)")
    docker_parser.add_argument("--mailpit-port", type=int, default=8025, help="Mailpit HTTP port (default: 8025)")
    docker_parser.add_argument("--git-repo", help="Git repository URL for runtime cloning")
    docker_parser.add_argument("--git-subdir", help="Subdirectory to clone from git repo")

    # Docker profile management
    docker_profiles = subparsers.add_parser("docker-profiles", help="Manage Docker export profiles")
    docker_profiles_sub = docker_profiles.add_subparsers(dest="profile_action", help="Profile actions")

    # List profiles
    docker_profiles_sub.add_parser("list", help="List saved Docker export profiles")

    # Delete profile
    docker_profile_delete = docker_profiles_sub.add_parser("delete", help="Delete a Docker export profile")
    docker_profile_delete.add_argument("name", help="Profile name to delete")

    # Sync command
    sync_parser = subparsers.add_parser("sync", help="Sync orders between Odoo instances")
    sync_subparsers = sync_parser.add_subparsers(dest="sync_action", help="Sync actions")

    # Sync run
    sync_run = sync_subparsers.add_parser("run", help="Run sync from source to target")
    sync_run.add_argument("--source", "-s", required=True, help="Source connection name (production)")
    sync_run.add_argument("--target", "-t", required=True, help="Target connection name (replica with allow_sync)")
    sync_run.add_argument("--batch-size", type=int, default=100, help="Batch size for sync (default: 100)")
    sync_run.add_argument("--no-deletes", action="store_true", help="Skip delete detection")
    sync_run.add_argument("--from-date", help="Only sync records modified after this date (YYYY-MM-DD HH:MM:SS). Use for initial sync after backup restore.")

    # Sync stats
    sync_stats = sync_subparsers.add_parser("stats", help="Show sync statistics")
    sync_stats.add_argument("--source", "-s", required=True, help="Source connection name")
    sync_stats.add_argument("--target", "-t", required=True, help="Target connection name")

    # Sync clear
    sync_clear = sync_subparsers.add_parser("clear", help="Clear sync mappings")
    sync_clear.add_argument("--source", "-s", help="Source connection name")
    sync_clear.add_argument("--target", "-t", help="Target connection name")
    sync_clear.add_argument("--confirm", action="store_true", help="Confirm clearing mappings")

    # GUI command (explicit)
    gui_parser = subparsers.add_parser("gui", help="Launch GUI interface")

    return parser


def handle_cli(parser, args):
    """Handle CLI-specific logic"""
    from .core.backup_restore import OdooBench
    from .db.connection_manager import ConnectionManager
    from .utils.config import Config

    if not args.command and not args.gui and not args.cli:
        # No command and no GUI available, show help
        parser.print_help()
        sys.exit(1)

    if args.gui:
        # Explicit GUI request
        launch_gui()
    elif not args.command:
        # --cli flag but no command
        parser.print_help()
        sys.exit(1)
    elif args.command == "gui":
        launch_gui()
    elif args.command == "backup":
        handle_backup(args)
    elif args.command == "restore":
        handle_restore(args)
    elif args.command == "connections":
        handle_connections(args)
    elif args.command == "from-config":
        handle_from_config(args)
    elif args.command == "docker-export":
        handle_docker_export(args)
    elif args.command == "docker-profiles":
        handle_docker_profiles(args)
    elif args.command == "sync":
        handle_sync(args)
    else:
        parser.print_help()
        sys.exit(1)


def launch_gui():
    """Launch the GUI interface"""
    from .gui_launcher import main as gui_main
    gui_main()


def handle_backup(args):
    """Handle backup command"""
    from .core.backup_restore import OdooBench
    from .db.connection_manager import ConnectionManager
    from .utils.config import Config

    conn_manager = ConnectionManager()
    config = Config()

    # Build configuration
    backup_config = {}

    if args.connection:
        # Load from saved connection (preferred method)
        connections = conn_manager.list_connections()
        conn = next((c for c in connections if c["name"] == args.connection), None)
        if not conn:
            print(f"Error: Connection '{args.connection}' not found")
            print("\nAvailable connections:")
            for c in connections:
                print(f"  - {c['name']}")
            print("\nUse 'odoobench --cli connections save' to create a new connection")
            sys.exit(1)

        conn_data = conn_manager.get_odoo_connection(conn["id"])
        backup_config.update(
            {
                "db_name": args.name or conn_data["database"],  # Allow override with --name
                "db_host": conn_data["host"],
                "db_port": conn_data["port"],
                "db_user": conn_data["username"],
                "db_password": conn_data["password"],
                "filestore_path": conn_data["filestore_path"],
            }
        )

        if not backup_config["db_name"]:
            print("Error: Database name not specified. Use --name to specify the database to backup")
            sys.exit(1)

        print(f"Using connection: {args.connection}")
        print(f"Backing up database: {backup_config['db_name']}")
    else:
        # Manual configuration (backward compatibility)
        if not args.name:
            print("Error: Database name is required when not using a connection profile")
            print("Use --name to specify the database or --connection to use a saved profile")
            sys.exit(1)

        password = args.password
        if not password:
            password = getpass.getpass("Database password: ")

        backup_config = {
            "db_name": args.name,
            "db_host": args.host,
            "db_port": args.port,
            "db_user": args.user,
            "db_password": password,
            "filestore_path": args.filestore,
        }

    backup_config["backup_filestore"] = not args.no_filestore
    backup_config["backup_dir"] = args.output_dir or config.get_backup_dir()

    # Perform backup
    try:
        backup_restore = OdooBench()
        backup_file = backup_restore.backup(backup_config)
        print(f"Backup completed successfully: {backup_file}")
    except Exception as e:
        print(f"Backup failed: {e}")
        sys.exit(1)


def handle_restore(args):
    """Handle restore command"""
    from .core.backup_restore import OdooBench
    from .db.connection_manager import ConnectionManager

    conn_manager = ConnectionManager()

    # Check if backup file exists
    if not Path(args.file).exists():
        print(f"Error: Backup file not found: {args.file}")
        sys.exit(1)

    # Build configuration
    restore_config = {}

    if args.connection:
        # Load from saved connection (preferred method)
        connections = conn_manager.list_connections()
        conn = next((c for c in connections if c["name"] == args.connection), None)
        if not conn:
            print(f"Error: Connection '{args.connection}' not found")
            print("\nAvailable connections:")
            for c in connections:
                print(f"  - {c['name']}")
            print("\nUse 'odoobench --cli connections save' to create a new connection")
            sys.exit(1)

        conn_data = conn_manager.get_odoo_connection(conn["id"])

        # Check if restore is allowed for this connection
        if not conn_data.get('allow_restore', False):
            print(f"Error: Restore operations are not allowed for connection '{args.connection}'")
            print("This is a safety feature to prevent accidental restores to production databases.")
            print("To enable restore for this connection, edit it and enable the 'Allow Restore' option.")
            sys.exit(1)

        restore_config.update(
            {
                "db_name": args.name or conn_data["database"],  # Allow override with --name
                "db_host": conn_data["host"],
                "db_port": conn_data["port"],
                "db_user": conn_data["username"],
                "db_password": conn_data["password"],
                "filestore_path": conn_data["filestore_path"],
            }
        )

        if not restore_config["db_name"]:
            print("Error: Database name not specified. Use --name to specify the target database")
            sys.exit(1)

        print(f"Using connection: {args.connection}")
        print(f"Restoring to database: {restore_config['db_name']}")
    else:
        # Manual configuration (backward compatibility)
        if not args.name:
            print("Error: Database name is required when not using a connection profile")
            print("Use --name to specify the target database or --connection to use a saved profile")
            sys.exit(1)

        password = args.password
        if not password:
            password = getpass.getpass("Database password: ")

        restore_config = {
            "db_name": args.name,
            "db_host": args.host,
            "db_port": args.port,
            "db_user": args.user,
            "db_password": password,
            "filestore_path": args.filestore,
        }

    restore_config["restore_filestore"] = not args.no_filestore
    restore_config["neutralize"] = args.neutralize

    # Perform restore
    try:
        backup_restore = OdooBench()
        success = backup_restore.restore(restore_config, args.file)
        if success:
            print(f"Restore completed successfully to database: {restore_config['db_name']}")
            if args.neutralize:
                print("Database has been neutralized for testing:")
                print("   - All outgoing mail servers disabled")
                print("   - All scheduled actions (crons) disabled")
                print("   - Payment acquirers disabled")
                print("   - Email queue cleared")
                print("   - Company names prefixed with [TEST]")
    except Exception as e:
        print(f"Restore failed: {e}")
        sys.exit(1)


def handle_connections(args):
    """Handle connections management"""
    from .db.connection_manager import ConnectionManager

    conn_manager = ConnectionManager()

    if args.conn_action == "list":
        connections = conn_manager.list_connections()
        if not connections:
            print("No saved connections found.")
        else:
            print("\nSaved Connections:")
            print("-" * 60)
            for conn in connections:
                # Get full connection details for Odoo connections
                if conn['type'] == 'odoo':
                    conn_data = conn_manager.get_odoo_connection(conn['id'])
                    allow_restore = conn_data.get('allow_restore', False)
                    restore_status = " [restore enabled]" if allow_restore else " [restore disabled]"
                else:
                    restore_status = ""

                print(f"  [{conn['type'].upper()}] {conn['name']}{restore_status}")
                print(f"    Host: {conn['host']}:{conn['port']}")
                if conn["type"] == "odoo" and conn.get("database"):
                    print(f"    Database: {conn['database']}")
                print(f"    User: {conn.get('username', 'N/A')}")
                print()

    elif args.conn_action == "save":
        password = args.password
        if password is None:
            password = getpass.getpass("Database password (optional): ")

        config = {
            "host": args.host,
            "port": args.port,
            "database": args.database,
            "username": args.user,
            "password": password if password else None,
            "filestore_path": args.filestore,
            "odoo_version": args.odoo_version,
            "allow_restore": args.allow_restore,
        }

        if conn_manager.save_odoo_connection(args.name, config):
            print(f"Connection '{args.name}' saved successfully")
            if args.allow_restore:
                print("Warning: Restore operations are enabled for this connection")
                print("   This should only be used for development/test databases")
            else:
                print("Restore operations are disabled (production safe)")
        else:
            print(f"Failed to save connection '{args.name}'")

    elif args.conn_action == "delete":
        connections = conn_manager.list_connections()
        conn = next((c for c in connections if c["name"] == args.name), None)
        if not conn:
            print(f"Error: Connection '{args.name}' not found")
            sys.exit(1)

        if conn["type"] == "odoo":
            success = conn_manager.delete_odoo_connection(conn["id"])
        elif conn["type"] == "ssh":
            success = conn_manager.delete_ssh_connection(conn["id"])
        else:
            success = False

        if success:
            print(f"Connection '{args.name}' deleted successfully")
        else:
            print(f"Failed to delete connection '{args.name}'")

    elif args.conn_action == "test":
        connections = conn_manager.list_connections()
        conn = next((c for c in connections if c["name"] == args.name), None)
        if not conn:
            print(f"Error: Connection '{args.name}' not found")
            sys.exit(1)

        if conn["type"] == "odoo":
            conn_data = conn_manager.get_odoo_connection(conn["id"])
            print(f"Testing connection '{args.name}'...")
            # Here you would implement actual connection testing
            # For now, just show the configuration
            print(f"  Host: {conn_data['host']}:{conn_data['port']}")
            print(f"  Database: {conn_data.get('database', 'N/A')}")
            print(f"  User: {conn_data['username']}")
            print("  Connection test not yet implemented")

    else:
        print("Error: No connection action specified")
        print("Use: connections list|save|delete|test")
        sys.exit(1)


def handle_from_config(args):
    """Handle operations from odoo.conf file"""
    from .core.backup_restore import OdooBench
    from .utils.config import Config

    config_file = Path(args.config_file)
    if not config_file.exists():
        print(f"Error: Config file not found: {args.config_file}")
        sys.exit(1)

    # Parse odoo.conf file
    import configparser
    odoo_config = configparser.ConfigParser()
    odoo_config.read(config_file)

    if "options" not in odoo_config:
        print("Error: Invalid odoo.conf file (no 'options' section)")
        sys.exit(1)

    options = odoo_config["options"]
    config = Config()

    # Build backup configuration from odoo.conf
    backup_config = {
        "db_name": options.get("db_name", ""),
        "db_host": options.get("db_host", "localhost"),
        "db_port": int(options.get("db_port", 5432)),
        "db_user": options.get("db_user", "odoo"),
        "db_password": options.get("db_password", ""),
        "filestore_path": options.get("data_dir", ""),
        "backup_filestore": bool(options.get("data_dir")),
        "backup_dir": args.output_dir or config.get_backup_dir(),
    }

    if not backup_config["db_name"]:
        print("Error: No database name found in config file")
        sys.exit(1)

    if args.backup:
        print(f"Creating backup from config: {args.config_file}")
        print(f"Database: {backup_config['db_name']}")
        try:
            backup_restore = OdooBench()
            backup_file = backup_restore.backup(backup_config)
            print(f"Backup completed successfully: {backup_file}")
        except Exception as e:
            print(f"Backup failed: {e}")
            sys.exit(1)
    else:
        print("Config file loaded. Use --backup to create a backup.")


def handle_docker_export(args):
    """Handle docker-export command"""
    from .db.odoo_connection_manager import OdooInstanceManager
    from .docker.exporter import DockerExporter
    from .utils.config import Config
    import json

    instance_manager = OdooInstanceManager()
    config = Config()

    # Get the source connection
    instance = instance_manager.get_instance_by_name(args.connection)
    if not instance:
        print(f"Error: Connection '{args.connection}' not found")
        print("\nAvailable connections:")
        for inst in instance_manager.list_instances():
            print(f"  - {inst['name']}")
        sys.exit(1)

    # Build the profile from saved profile or command-line args
    profile = {}

    if args.profile:
        # Load saved profile
        saved_profile = instance_manager.get_docker_export_profile_by_name(args.profile)
        if not saved_profile:
            print(f"Error: Docker export profile '{args.profile}' not found")
            print("\nAvailable profiles:")
            for p in instance_manager.list_docker_export_profiles():
                print(f"  - {p['name']}")
            sys.exit(1)
        profile = saved_profile
        print(f"Using Docker export profile: {args.profile}")
    else:
        # Build profile from command-line args
        if not args.source_dir:
            print("Error: --source-dir is required when not using a saved profile")
            sys.exit(1)
        if not args.subdirs:
            print("Error: --subdirs is required when not using a saved profile")
            sys.exit(1)

        profile = {
            'source_base_dir': args.source_dir,
            'source_subdirs': json.dumps(args.subdirs.split(',')),
            'venv_path': args.venv_path or '',
            'extra_files': json.dumps(args.extra_files.split(',')) if args.extra_files else '[]',
            'odoo_conf_path': args.odoo_conf_path or 'odoo/odoo.conf',
            'container_base_dir': '/opt/odoo/qlf',
            'postgres_version': args.pg_version,
            'python_version': args.python_version,
            'odoo_port': args.odoo_port,
            'mailpit_http_port': args.mailpit_port,
            'git_repo_url': args.git_repo or '',
            'git_clone_subdir': args.git_subdir or '',
        }

    # Override output directory if specified
    if args.output_dir:
        profile['output_dir'] = args.output_dir
    elif not profile.get('output_dir'):
        profile['output_dir'] = config.get_backup_dir()

    # Build source config from instance
    source_config = {
        'db_name': instance['db_name'],
        'db_host': instance['db_host'],
        'db_port': instance['db_port'],
        'db_user': instance['db_user'],
        'db_password': instance['db_password'],
        'filestore_path': instance['filestore_path'],
        'is_local': instance['is_local'],
        'host': instance['host'],
        'ssh_port': instance['ssh_port'],
        'ssh_username': instance['ssh_username'],
        'ssh_password': instance['ssh_password'],
        'ssh_key_path': instance['ssh_key_path'],
    }

    # Check for SSH connection requirement
    if not source_config['is_local']:
        source_config['use_ssh'] = True
        source_config['ssh_connection_id'] = instance['id']

    print(f"Creating Docker export for: {instance['name']}")
    print(f"Database: {source_config['db_name']}")
    print(f"Output directory: {profile['output_dir']}")
    print()

    try:
        exporter = DockerExporter(conn_manager=instance_manager)
        output_path = exporter.export(source_config, profile)
        print()
        print(f"Docker export completed successfully: {output_path}")
    except Exception as e:
        print(f"Docker export failed: {e}")
        sys.exit(1)


def handle_docker_profiles(args):
    """Handle docker-profiles command"""
    from .db.odoo_connection_manager import OdooInstanceManager

    instance_manager = OdooInstanceManager()

    if args.profile_action == "list":
        profiles = instance_manager.list_docker_export_profiles()
        if not profiles:
            print("No Docker export profiles found.")
        else:
            print("\nDocker Export Profiles:")
            print("-" * 60)
            for p in profiles:
                instance_name = p.get('instance_name', 'N/A')
                print(f"  {p['name']}")
                print(f"    Instance: {instance_name}")
                print(f"    Source: {p.get('source_base_dir', 'N/A')}")
                print(f"    Python: {p.get('python_version', '3.12')}")
                print(f"    PostgreSQL: {p.get('postgres_version', '16')}")
                print()

    elif args.profile_action == "delete":
        profile = instance_manager.get_docker_export_profile_by_name(args.name)
        if not profile:
            print(f"Error: Profile '{args.name}' not found")
            sys.exit(1)

        if instance_manager.delete_docker_export_profile(profile['id']):
            print(f"Profile '{args.name}' deleted successfully")
        else:
            print(f"Failed to delete profile '{args.name}'")
            sys.exit(1)

    else:
        print("Error: No profile action specified")
        print("Use: docker-profiles list|delete")
        sys.exit(1)


def handle_sync(args):
    """Handle sync command"""
    from .db.odoo_connection_manager import OdooInstanceManager

    instance_manager = OdooInstanceManager()

    if args.sync_action == "run":
        try:
            from .sync import SyncEngine
        except ImportError as e:
            print(f"Error: Could not import sync module: {e}")
            print("Make sure odoorpc is installed: pip install odoorpc")
            sys.exit(1)

        # Get source instance
        source = instance_manager.get_instance_by_name(args.source)
        if not source:
            print(f"Error: Source connection '{args.source}' not found")
            sys.exit(1)

        # Get target instance
        target = instance_manager.get_instance_by_name(args.target)
        if not target:
            print(f"Error: Target connection '{args.target}' not found")
            sys.exit(1)

        # Check allow_sync on target
        if not target.get('allow_sync'):
            print(f"Error: Target connection '{args.target}' does not have 'Allow Sync' enabled")
            print("Edit the connection to enable sync operations for this target.")
            sys.exit(1)

        print(f"Order Sync")
        print(f"  Source: {args.source} ({source.get('db_name', 'N/A')})")
        print(f"  Target: {args.target} ({target.get('db_name', 'N/A')})")
        print(f"  Batch size: {args.batch_size}")
        print(f"  Delete detection: {'disabled' if args.no_deletes else 'enabled'}")
        if args.from_date:
            print(f"  Only records after: {args.from_date}")
        print()

        # Create sync engine with CLI callbacks
        def progress_callback(percent, message):
            print(f"  [{percent:3d}%] {message}")

        def log_callback(message, level):
            prefix = {'error': 'ERROR', 'warning': 'WARN', 'success': 'OK'}.get(level, 'INFO')
            print(f"  [{prefix}] {message}")

        engine = SyncEngine(
            instance_manager=instance_manager,
            progress_callback=progress_callback,
            log_callback=log_callback,
        )

        # Connect
        if not engine.connect(source['id'], target['id']):
            print("Failed to connect to one or both instances")
            sys.exit(1)

        # Run sync
        try:
            results = engine.run_full_sync(
                include_deletes=not args.no_deletes,
                batch_size=args.batch_size,
                sync_from_date=args.from_date,
            )
            engine.disconnect()

            # Print summary
            print()
            print("Sync Complete:")
            for model, stats in results.get('sync', {}).items():
                print(f"  {model}:")
                print(f"    Created: {stats.get('created', 0)}")
                print(f"    Updated: {stats.get('updated', 0)}")
                print(f"    Errors: {stats.get('errors', 0)}")

            for model, count in results.get('deletes', {}).items():
                if count > 0:
                    print(f"  {model}: {count} deleted")

            if results.get('errors'):
                print(f"  Errors: {len(results['errors'])}")
                for err in results['errors']:
                    print(f"    - {err}")

        except Exception as e:
            print(f"Sync failed: {e}")
            sys.exit(1)

    elif args.sync_action == "stats":
        # Get source instance
        source = instance_manager.get_instance_by_name(args.source)
        if not source:
            print(f"Error: Source connection '{args.source}' not found")
            sys.exit(1)

        # Get target instance
        target = instance_manager.get_instance_by_name(args.target)
        if not target:
            print(f"Error: Target connection '{args.target}' not found")
            sys.exit(1)

        stats = instance_manager.get_sync_stats(source['id'], target['id'])

        print(f"Sync Statistics")
        print(f"  Source: {args.source}")
        print(f"  Target: {args.target}")
        print()

        if not stats:
            print("  No records synced yet.")
        else:
            print("  Synced Records:")
            for model, count in stats.items():
                print(f"    {model}: {count}")

        # Show last sync time
        last_sync = instance_manager.get_last_sync_time('sale.order', source['id'], target['id'])
        print(f"\n  Last sync: {last_sync or 'Never'}")

    elif args.sync_action == "clear":
        if not args.confirm:
            print("Error: Use --confirm to confirm clearing sync mappings")
            print("This will clear all sync tracking data.")
            sys.exit(1)

        source_id = None
        target_id = None

        if args.source:
            source = instance_manager.get_instance_by_name(args.source)
            if source:
                source_id = source['id']

        if args.target:
            target = instance_manager.get_instance_by_name(args.target)
            if target:
                target_id = target['id']

        if not source_id and not target_id:
            print("Error: Specify at least one of --source or --target")
            sys.exit(1)

        count = instance_manager.delete_sync_mappings_for_instance(
            source_instance_id=source_id,
            target_instance_id=target_id,
        )
        print(f"Cleared {count} sync mapping(s)")

    else:
        print("Error: No sync action specified")
        print("Use: sync run|stats|clear")
        sys.exit(1)


if __name__ == "__main__":
    main()
