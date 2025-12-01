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
    # Check if we're in a pipe or being redirected
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False

    # Check for display
    if not os.environ.get('DISPLAY') and not sys.platform.startswith('win') and not sys.platform == 'darwin':
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

    # GUI command (explicit)
    gui_parser = subparsers.add_parser("gui", help="Launch GUI interface")

    return parser


def handle_cli(parser, args):
    """Handle CLI-specific logic"""
    from .core.backup_restore import OdooBackupRestore
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
    else:
        parser.print_help()
        sys.exit(1)


def launch_gui():
    """Launch the GUI interface"""
    try:
        import tkinter as tk
        from .gui.main_window import OdooBackupRestoreGUI

        root = tk.Tk()
        app = OdooBackupRestoreGUI(root)
        root.mainloop()
    except ImportError as e:
        print("Error: GUI dependencies not available.")
        print("Please install tkinter: sudo apt-get install python3-tk")
        print(f"Error details: {e}")
        print("\nYou can use CLI mode with: odoobench --cli [command]")
        sys.exit(1)


def handle_backup(args):
    """Handle backup command"""
    from .core.backup_restore import OdooBackupRestore
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
        backup_restore = OdooBackupRestore()
        backup_file = backup_restore.backup(backup_config)
        print(f"Backup completed successfully: {backup_file}")
    except Exception as e:
        print(f"Backup failed: {e}")
        sys.exit(1)


def handle_restore(args):
    """Handle restore command"""
    from .core.backup_restore import OdooBackupRestore
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
        backup_restore = OdooBackupRestore()
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
    from .core.backup_restore import OdooBackupRestore
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
            backup_restore = OdooBackupRestore()
            backup_file = backup_restore.backup(backup_config)
            print(f"Backup completed successfully: {backup_file}")
        except Exception as e:
            print(f"Backup failed: {e}")
            sys.exit(1)
    else:
        print("Config file loaded. Use --backup to create a backup.")


if __name__ == "__main__":
    main()
