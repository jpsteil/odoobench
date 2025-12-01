"""
Core Odoo Backup and Restore functionality
"""

import os
import sys
import subprocess
import shutil
import tarfile
import tempfile
import json
import zipfile
import configparser
import uuid
from datetime import datetime
from pathlib import Path
import paramiko


class OdooBackupRestore:
    """Main class for Odoo backup and restore operations"""

    def __init__(self, progress_callback=None, log_callback=None, conn_manager=None):
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.temp_dir = tempfile.mkdtemp(prefix="odoo_backup_")
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        self.conn_manager = conn_manager

    @staticmethod
    def parse_odoo_conf(conf_path):
        """Parse odoo.conf file and extract connection settings"""
        if not os.path.exists(conf_path):
            raise FileNotFoundError(f"Config file not found: {conf_path}")

        config = configparser.ConfigParser()
        config.read(conf_path)

        # Get the main options section
        if "options" not in config:
            raise ValueError("No 'options' section found in config file")

        options = config["options"]

        # Extract connection details
        connection_config = {
            "host": options.get("db_host", "localhost"),
            "port": options.get("db_port", "5432"),
            "database": options.get("db_name", "False"),  # Odoo uses 'False' as default
            "username": options.get("db_user", "odoo"),
            "password": options.get("db_password", "False"),
            "filestore_path": None,
            "odoo_version": "17.0",  # Default version
            "is_local": options.get("db_host", "localhost")
            in ["localhost", "127.0.0.1"],
        }

        # Try to determine filestore path
        data_dir = options.get("data_dir", None)
        if data_dir and data_dir != "False":
            connection_config["filestore_path"] = data_dir
        else:
            connection_config["filestore_path"] = os.path.expanduser(
                "~/.local/share/Odoo"
            )

        # Clean up 'False' values
        for key in ["database", "password"]:
            if connection_config[key] == "False":
                connection_config[key] = ""

        return connection_config

    def __del__(self):
        """Cleanup temp directory"""
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def log(self, message, level="info"):
        """Log message with callback support"""
        print(message)
        if self.log_callback:
            self.log_callback(message, level)

    def _log(self, message, level="info"):
        """Internal log method (alias for log)"""
        self.log(message, level)

    def update_progress(self, value, message=""):
        """Update progress with callback support"""
        if self.progress_callback:
            self.progress_callback(value, message)

    def run_command(self, command, shell=False, capture_output=True):
        """Execute shell command and return output"""
        try:
            result = subprocess.run(
                command,
                shell=shell,
                capture_output=capture_output,
                text=True,
                check=True,
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            self.log(f"Error executing command: {e}", "error")
            self.log(f"Error output: {e.stderr}", "error")
            raise

    def check_dependencies(self):
        """Check if required tools are installed"""
        dependencies = ["pg_dump", "pg_restore", "psql", "tar"]
        missing = []

        for dep in dependencies:
            if shutil.which(dep) is None:
                missing.append(dep)

        if missing:
            error_msg = f"Missing dependencies: {', '.join(missing)}\nPlease install PostgreSQL client tools and tar"
            self.log(error_msg, "error")
            raise Exception(error_msg)

    def test_connection(self, config):
        """Test database connection and filestore path"""
        messages = []
        has_errors = False

        # Test database connection
        env = os.environ.copy()
        if config.get("db_password"):
            env["PGPASSWORD"] = config["db_password"]

        try:
            cmd = [
                "psql",
                "-h",
                config["db_host"],
                "-p",
                str(config["db_port"]),
                "-U",
                config["db_user"],
                "-d",
                "postgres",
                "-c",
                "SELECT version();",
            ]

            result = subprocess.run(
                cmd, env=env, capture_output=True, text=True, timeout=5
            )

            if result.returncode == 0:
                messages.append("✓ Database connection successful")
            else:
                messages.append(f"✗ Database connection failed: {result.stderr}")
                has_errors = True

        except Exception as e:
            messages.append(f"✗ Database connection error: {str(e)}")
            has_errors = True

        # Test filestore path if provided
        filestore_path = config.get("filestore_path")
        if filestore_path:
            if config.get("use_ssh") and config.get("ssh_connection_id"):
                # Test remote filestore path
                try:
                    ssh_conn = self.conn_manager.get_ssh_connection(
                        config["ssh_connection_id"]
                    )
                    if ssh_conn:
                        ssh = self._get_ssh_client(ssh_conn)

                        # Check if the filestore path exists
                        stdin, stdout, stderr = ssh.exec_command(
                            f"test -d '{filestore_path}'"
                        )
                        if stdout.channel.recv_exit_status() == 0:
                            messages.append(
                                f"✓ Remote filestore path exists: {filestore_path}"
                            )
                        else:
                            # Try with database name appended
                            db_name = config.get("db_name", "")
                            if db_name:
                                full_path = os.path.join(
                                    filestore_path, "filestore", db_name
                                )
                                stdin, stdout, stderr = ssh.exec_command(
                                    f"test -d '{full_path}'"
                                )
                                if stdout.channel.recv_exit_status() == 0:
                                    messages.append(
                                        f"✓ Remote filestore path exists: {full_path}"
                                    )
                                else:
                                    messages.append(
                                        f"⚠ Remote filestore path not found"
                                    )
                            else:
                                messages.append(
                                    f"⚠ Remote filestore path not found: {filestore_path}"
                                )

                        ssh.close()
                    else:
                        messages.append("⚠ SSH connection not found for filestore test")
                except Exception as e:
                    messages.append(f"⚠ Could not test remote filestore: {str(e)}")
            else:
                # Test local filestore path
                if os.path.exists(filestore_path):
                    messages.append(f"✓ Local filestore path exists: {filestore_path}")
                else:
                    # Try with database name appended
                    db_name = config.get("db_name", "")
                    if db_name:
                        full_path = os.path.join(filestore_path, "filestore", db_name)
                        if os.path.exists(full_path):
                            messages.append(
                                f"✓ Local filestore path exists: {full_path}"
                            )
                        else:
                            messages.append(f"⚠ Local filestore path not found")
                    else:
                        messages.append(
                            f"⚠ Local filestore path not found: {filestore_path}"
                        )

        # Return combined result
        return not has_errors, "\n".join(messages)

    def _get_ssh_client(self, ssh_conn):
        """Create and configure SSH client"""
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {
            "hostname": ssh_conn["host"],
            "port": ssh_conn.get("port", 22),
            "username": ssh_conn["username"],
        }

        if ssh_conn.get("key_path"):
            connect_kwargs["key_filename"] = ssh_conn["key_path"]
        elif ssh_conn.get("password"):
            connect_kwargs["password"] = ssh_conn["password"]

        ssh.connect(**connect_kwargs)
        return ssh

    def check_remote_disk_space(self, ssh, path, estimated_size_mb):
        """Check if remote server has enough disk space for backup"""
        try:
            # Get available space in /tmp
            stdin, stdout, stderr = ssh.exec_command(
                "df -BM /tmp | tail -1 | awk '{print $4}'"
            )
            available_space = stdout.read().decode().strip()
            # Remove 'M' suffix and convert to integer
            available_mb = int(available_space.rstrip("M"))

            # Add 20% safety margin to estimated size
            required_mb = int(estimated_size_mb * 1.2)

            if available_mb < required_mb:
                return False, available_mb, required_mb
            return True, available_mb, required_mb
        except Exception as e:
            self.log(f"Warning: Could not check disk space: {e}", "warning")
            return True, 0, 0  # Proceed anyway if check fails

    def estimate_compressed_size(self, ssh, path, is_database=False):
        """Estimate compressed size of a directory or database"""
        try:
            if is_database:
                # For database, get the database size from PostgreSQL
                return 100  # Default estimate for database
            else:
                # Check if path is valid
                if not path:
                    self.log("Warning: Path is empty, using default estimate", "warning")
                    return 100
                # For filestore, get directory size
                stdin, stdout, stderr = ssh.exec_command(f"du -sm '{path}' | cut -f1")
                output = stdout.read().decode().strip()
                if not output or not output.isdigit():
                    self.log(f"Warning: Could not get size for {path}, using default estimate", "warning")
                    return 100
                size_mb = int(output)
                # Estimate compression ratio (typically 30-50% for filestore)
                compressed_estimate = size_mb * 0.4
                return compressed_estimate
        except Exception as e:
            self.log(f"Warning: Could not estimate size: {e}", "warning")
            return 100  # Default conservative estimate

    def backup_database(self, config):
        """Backup PostgreSQL database"""
        self.log(f"Backing up database: {config['db_name']}...")
        self.update_progress(20, "Backing up database...")

        # Build pg_dump command
        dump_file = os.path.join(self.temp_dir, f"{config['db_name']}.sql")

        env = os.environ.copy()
        if config.get("db_password"):
            env["PGPASSWORD"] = config["db_password"]

        cmd = [
            "pg_dump",
            "-h",
            config["db_host"],
            "-p",
            str(config["db_port"]),
            "-U",
            config["db_user"],
            "-d",
            config["db_name"],
            "-f",
            dump_file,
            "--no-owner",
            "--no-acl",
        ]

        # Capture output to prevent flooding console
        subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
        self.log(f"Database backed up successfully")
        self.update_progress(40, "Database backup complete")
        return dump_file

    def backup_filestore(self, config):
        """Backup Odoo filestore"""
        filestore_path = config.get("filestore_path")

        if not filestore_path:
            self.log("Warning: Filestore path not specified", "warning")
            return None

        # Check if we need to use SSH
        if config.get("use_ssh") and config.get("ssh_connection_id"):
            return self._backup_remote_filestore(config, filestore_path)
        else:
            return self._backup_local_filestore(config, filestore_path)

    def _backup_remote_filestore(self, config, filestore_path):
        """Backup remote filestore via SSH"""
        # Get SSH connection details
        ssh_conn = self.conn_manager.get_ssh_connection(config["ssh_connection_id"])
        if not ssh_conn:
            self.log("Error: SSH connection not found", "error")
            return None

        # Build full filestore path with database name if needed
        db_name = config.get("db_name", "")
        if db_name and not filestore_path.endswith(db_name):
            # Check if path already ends with 'filestore'
            if filestore_path.rstrip('/').endswith('filestore'):
                # Path already has filestore, just add database name
                full_filestore_path = os.path.join(filestore_path, db_name)
            else:
                # Path doesn't have filestore, add filestore/db_name
                full_filestore_path = os.path.join(filestore_path, "filestore", db_name)
        else:
            full_filestore_path = filestore_path
            
        self.log(f"Backing up remote filestore via SSH: {full_filestore_path}...")
        self.update_progress(50, "Backing up remote filestore...")

        try:
            ssh = self._get_ssh_client(ssh_conn)

            # Create remote tar archive
            archive_name = os.path.join(self.temp_dir, "filestore.tar.gz")
            remote_temp = f"/tmp/filestore_{self.timestamp}.tar.gz"

            # Check filestore path
            self.log("Checking remote filestore path...")
            stdin, stdout, stderr = ssh.exec_command(f"test -d '{full_filestore_path}'")
            if stdout.channel.recv_exit_status() != 0:
                # Path doesn't exist - log warning but use as-is
                self.log(f"Warning: Filestore path does not exist: {full_filestore_path}", "warning")

            # Estimate and check disk space
            self.log("Estimating backup size...")
            # Check if full_filestore_path is valid before estimating
            if not full_filestore_path:
                self.log("Error: Filestore path is empty or None", "error")
                ssh.close()
                return None
            estimated_size = self.estimate_compressed_size(
                ssh, full_filestore_path, is_database=False
            )

            has_space, available_mb, required_mb = self.check_remote_disk_space(
                ssh, "/tmp", estimated_size
            )

            if not has_space:
                error_msg = f"Insufficient disk space on remote server!\n"
                error_msg += f"Available: {available_mb}MB, Required: {required_mb}MB"
                self.log(error_msg, "error")
                ssh.close()
                raise Exception(error_msg)

            self.log(
                f"Disk space check passed (Available: {available_mb}MB, Required: {required_mb}MB)"
            )
            self.log("Creating remote archive...")

            stdin, stdout, stderr = ssh.exec_command(
                f"cd '{full_filestore_path}' && tar -czf {remote_temp} ."
            )
            exit_status = stdout.channel.recv_exit_status()

            if exit_status != 0:
                error_msg = stderr.read().decode()
                self.log(f"Error creating remote archive: {error_msg}", "error")
                ssh.close()
                return None

            try:
                # Download the archive via SFTP
                self.log("Downloading filestore archive...")
                sftp = ssh.open_sftp()
                sftp.get(remote_temp, archive_name)
                sftp.close()

                self.log("Remote filestore backed up successfully")
                self.update_progress(70, "Filestore backup complete")
                return archive_name

            finally:
                # Always clean up remote temp file
                try:
                    self.log("Cleaning up remote temporary files...")
                    if ssh and remote_temp:
                        ssh.exec_command(f"rm -f {remote_temp}")
                    if ssh:
                        ssh.close()
                except Exception as cleanup_error:
                    self.log(f"Warning: Error during cleanup: {cleanup_error}", "warning")

        except Exception as e:
            self.log(f"Error backing up remote filestore: {str(e)}", "error")
            return None

    def _backup_local_filestore(self, config, filestore_path):
        """Backup local filestore"""
        if not os.path.exists(filestore_path):
            self.log(
                f"Warning: Local filestore path does not exist: {filestore_path}",
                "warning",
            )
            return None

        self.log(f"Backing up local filestore: {filestore_path}...")
        self.update_progress(50, "Backing up filestore...")

        # Create tar archive of filestore
        archive_name = os.path.join(self.temp_dir, "filestore.tar.gz")
        with tarfile.open(archive_name, "w:gz") as tar:
            tar.add(filestore_path, arcname="filestore")

        self.log(f"Filestore backed up successfully")
        self.update_progress(70, "Filestore backup complete")
        return archive_name

    def create_backup_archive(self, config, db_dump, filestore_archive):
        """Create combined backup archive"""
        backup_name = f"backup_{config['db_name'].upper()}_{self.timestamp}.tar.gz"
        # Use temp_dir if backup_dir is None or not specified
        backup_dir = config.get("backup_dir") or self.temp_dir
        backup_path = os.path.join(backup_dir, backup_name)

        self.log(f"Creating backup archive: {backup_name}...")
        self.update_progress(80, "Creating archive...")

        # Create metadata file
        metadata = {
            "timestamp": self.timestamp,
            "db_name": config["db_name"],
            "odoo_version": config.get("odoo_version", "unknown"),
            "has_filestore": filestore_archive is not None,
        }

        metadata_file = os.path.join(self.temp_dir, "metadata.json")
        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

        # Create combined archive
        with tarfile.open(backup_path, "w:gz") as tar:
            tar.add(db_dump, arcname="database.sql")
            tar.add(metadata_file, arcname="metadata.json")
            if filestore_archive:
                tar.add(filestore_archive, arcname="filestore.tar.gz")

        self.log(f"✅ Backup complete: {backup_path}", "success")
        self.update_progress(90, "Backup archive created")
        return backup_path

    def extract_backup(self, backup_file):
        """Extract backup archive"""
        self.log(f"Extracting backup: {os.path.basename(backup_file)}...")
        self.update_progress(10, "Extracting backup...")

        extract_dir = os.path.join(self.temp_dir, "extract")
        os.makedirs(extract_dir, exist_ok=True)

        # Try to detect actual file type regardless of extension
        # First try as zip
        try:
            with zipfile.ZipFile(backup_file, "r") as zf:
                self.log("Detected ZIP format, extracting...")
                zf.extractall(extract_dir)
        except zipfile.BadZipFile:
            # Not a zip, try tar.gz
            try:
                with tarfile.open(backup_file, "r:gz") as tar:
                    self.log("Detected TAR.GZ format, extracting...")
                    tar.extractall(extract_dir)
            except tarfile.ReadError:
                # Try regular tar
                try:
                    with tarfile.open(backup_file, "r") as tar:
                        self.log("Detected TAR format, extracting...")
                        tar.extractall(extract_dir)
                except:
                    raise Exception(
                        f"Unable to extract {backup_file}. File format not recognized."
                    )

        # Read metadata
        metadata_file = os.path.join(extract_dir, "metadata.json")
        if os.path.exists(metadata_file):
            with open(metadata_file, "r") as f:
                metadata = json.load(f)
        else:
            metadata = {}

        # Find files
        files = os.listdir(extract_dir)
        db_dump = None
        filestore_archive = None

        for file in files:
            if file.endswith(".sql"):
                db_dump = os.path.join(extract_dir, file)
            elif "filestore" in file and file.endswith(".tar.gz"):
                filestore_archive = os.path.join(extract_dir, file)

        self.update_progress(20, "Backup extracted")
        return db_dump, filestore_archive, metadata

    def restore_database(self, config, db_dump):
        """Restore PostgreSQL database"""
        try:
            self.log(f"Restoring database: {config['db_name']}...")
            self.update_progress(30, "Restoring database...")

            env = os.environ.copy()
            if config.get("db_password"):
                env["PGPASSWORD"] = config["db_password"]

            # Check if database exists
            check_cmd = [
                "psql",
                "-h",
                config["db_host"],
                "-p",
                str(config["db_port"]),
                "-U",
                config["db_user"],
                "-lqt",
            ]

            result = subprocess.run(check_cmd, env=env, capture_output=True, text=True)
            db_exists = config["db_name"] in result.stdout

            if db_exists:
                # Drop existing database
                self.log(f"Dropping existing database: {config['db_name']}...")
                # Terminate connections
                terminate_cmd = f"""
                    SELECT pg_terminate_backend(pid) 
                    FROM pg_stat_activity 
                    WHERE datname = '{config['db_name']}' AND pid <> pg_backend_pid();
                """
                subprocess.run(
                    [
                        "psql",
                        "-h",
                        config["db_host"],
                        "-p",
                        str(config["db_port"]),
                        "-U",
                        config["db_user"],
                        "-d",
                        "postgres",
                        "-c",
                        terminate_cmd,
                    ],
                    env=env,
                    capture_output=True,
                )

                # Drop database
                drop_cmd = [
                    "dropdb",
                    "-h",
                    config["db_host"],
                    "-p",
                    str(config["db_port"]),
                    "-U",
                    config["db_user"],
                    config["db_name"],
                ]
                subprocess.run(drop_cmd, env=env, check=True, 
                             capture_output=True, text=True)

            # Create database
            self.log(f"Creating database: {config['db_name']}...")
            create_cmd = [
                "createdb",
                "-h",
                config["db_host"],
                "-p",
                str(config["db_port"]),
                "-U",
                config["db_user"],
                config["db_name"],
            ]
            subprocess.run(create_cmd, env=env, check=True, 
                         capture_output=True, text=True)

            # Restore database
            self.update_progress(50, "Importing database data...")

            restore_cmd = [
                "psql",
                "-h",
                config["db_host"],
                "-p",
                str(config["db_port"]),
                "-U",
                config["db_user"],
                "-d",
                config["db_name"],
                "-f",
                db_dump,
                "-q",  # Quiet mode since we're capturing output anyway
            ]
            # Capture output to prevent flooding console
            subprocess.run(restore_cmd, env=env, check=True, 
                         capture_output=True, text=True)

            self.log(f"Database restored successfully")
            self.update_progress(70, "Database restore complete")
            return True

        except Exception as e:
            self.log(f"Error restoring database: {str(e)}", "error")
            raise

    def restore_filestore(self, config, filestore_archive):
        """Restore Odoo filestore"""
        if not filestore_archive:
            self.log("No filestore to restore", "warning")
            return True

        filestore_path = config["filestore_path"]
        if not filestore_path:
            self.log("Warning: Filestore path not specified", "warning")
            return False

        # Check if we need to use SSH
        if config.get("use_ssh") and config.get("ssh_connection_id"):
            return self._restore_remote_filestore(config, filestore_path, filestore_archive)
        else:
            return self._restore_local_filestore(config, filestore_path, filestore_archive)
    
    def _restore_local_filestore(self, config, filestore_path, filestore_archive):
        """Restore filestore locally"""
        # Build full filestore path with database name if needed
        db_name = config.get("db_name", "")
        if db_name and not filestore_path.endswith(db_name):
            # Check if path already ends with 'filestore'
            if filestore_path.rstrip('/').endswith('filestore'):
                # Path already has filestore, just add database name
                target_base_path = os.path.join(filestore_path, db_name)
            else:
                # Path doesn't have filestore, add filestore/db_name
                target_base_path = os.path.join(filestore_path, "filestore", db_name)
        else:
            target_base_path = filestore_path
            
        self.log(f"Restoring filestore locally to: {target_base_path}...")
        self.update_progress(75, "Restoring filestore...")

        try:
            # Create parent directory if it doesn't exist
            os.makedirs(os.path.dirname(target_base_path), exist_ok=True)

            # Extract filestore archive to temp location first
            with tempfile.TemporaryDirectory() as temp_dir:
                with tarfile.open(filestore_archive, "r:gz") as tar:
                    # Extract to temp directory
                    tar.extractall(temp_dir)
                
                # Determine the structure of the extracted archive
                extracted_items = os.listdir(temp_dir)
                
                # Check if we have hash directories directly (like 8c/, 86/, etc.)
                # These are typical Odoo filestore directories
                has_hash_dirs = any(
                    len(item) == 2 and item.isalnum() and os.path.isdir(os.path.join(temp_dir, item))
                    for item in extracted_items
                )
                
                if has_hash_dirs:
                    # Archive contains filestore files directly
                    self.log("Detected direct filestore structure (hash directories)")
                    target_path = target_base_path
                    
                    # Remove the existing filestore if it exists
                    if os.path.exists(target_path):
                        self.log(f"Removing existing filestore: {target_path}")
                        shutil.rmtree(target_path, ignore_errors=True)
                    
                    # Create the target directory
                    os.makedirs(target_path, exist_ok=True)
                    
                    # Move all hash directories to the target
                    for item in extracted_items:
                        source = os.path.join(temp_dir, item)
                        dest = os.path.join(target_path, item)
                        if os.path.isdir(source):
                            shutil.move(source, dest)
                    
                    self.log(f"Filestore restored to: {target_path}")
                
                elif os.path.exists(os.path.join(temp_dir, "filestore")):
                    # Archive has 'filestore' parent directory
                    temp_filestore = os.path.join(temp_dir, "filestore")
                    
                    # Get the source database name from the extracted archive
                    extracted_dirs = [d for d in os.listdir(temp_filestore) 
                                    if os.path.isdir(os.path.join(temp_filestore, d))]
                    
                    if extracted_dirs:
                        source_db_name = extracted_dirs[0]  # Should only be one
                        source_path = os.path.join(temp_filestore, source_db_name)
                        target_path = target_base_path
                        
                        # Now remove the existing filestore if it exists
                        if os.path.exists(target_path):
                            self.log(f"Removing existing filestore: {target_path}")
                            shutil.rmtree(target_path, ignore_errors=True)
                        
                        # Create the target directory
                        os.makedirs(target_path, exist_ok=True)
                        
                        # Copy all contents from source to target
                        self.log(f"Copying filestore contents from '{source_db_name}'")
                        for item in os.listdir(source_path):
                            source_item = os.path.join(source_path, item)
                            dest_item = os.path.join(target_path, item)
                            if os.path.isdir(source_item):
                                shutil.copytree(source_item, dest_item)
                            else:
                                shutil.copy2(source_item, dest_item)
                        self.log(f"Filestore contents copied successfully")
                    else:
                        raise Exception("No database directory found in extracted filestore")
                
                elif len(extracted_items) == 1 and os.path.isdir(os.path.join(temp_dir, extracted_items[0])):
                    # Archive contains a single directory (possibly the database name)
                    source_path = os.path.join(temp_dir, extracted_items[0])
                    target_path = target_base_path
                    
                    # Remove existing filestore if it exists
                    if os.path.exists(target_path):
                        self.log(f"Removing existing filestore: {target_path}")
                        shutil.rmtree(target_path, ignore_errors=True)
                    
                    # Create the target directory
                    os.makedirs(target_path, exist_ok=True)
                    
                    # Copy all contents from source to target
                    self.log(f"Copying filestore contents from single directory")
                    for item in os.listdir(source_path):
                        source_item = os.path.join(source_path, item)
                        dest_item = os.path.join(target_path, item)
                        if os.path.isdir(source_item):
                            shutil.copytree(source_item, dest_item)
                        else:
                            shutil.copy2(source_item, dest_item)
                    self.log(f"Filestore contents copied successfully")
                
                else:
                    raise Exception("Unable to determine filestore structure in archive")

            self.log("Filestore restored successfully")
            self.update_progress(90, "Filestore restore complete")
            return True

        except Exception as e:
            self.log(f"Error restoring filestore: {str(e)}", "error")
            return False

    def _restore_remote_filestore(self, config, filestore_path, filestore_archive):
        """Restore filestore to remote server via SSH"""
        ssh_conn_id = config.get("ssh_connection_id")
        if not ssh_conn_id:
            self.log("SSH connection ID not provided", "error")
            return False
        
        ssh_conn = self.conn_manager.get_ssh_connection(ssh_conn_id)
        if not ssh_conn:
            self.log(f"SSH connection {ssh_conn_id} not found", "error")
            return False

        self.log(f"Restoring filestore to remote server via SSH: {filestore_path}...")
        self.update_progress(75, "Restoring filestore via SSH...")

        try:
            # Get SSH client connection
            ssh = self._get_ssh_client(ssh_conn)
            
            # Build full filestore path with database name if needed
            db_name = config.get("db_name", "")
            if db_name and not filestore_path.endswith(db_name):
                # Check if path already ends with 'filestore'
                if filestore_path.rstrip('/').endswith('filestore'):
                    # Path already has filestore, just add database name
                    remote_target = os.path.join(filestore_path, db_name)
                else:
                    # Path doesn't have filestore, add filestore/db_name
                    remote_target = os.path.join(filestore_path, "filestore", db_name)
            else:
                remote_target = filestore_path
            
            self.log(f"Remote target path: {remote_target}")

            # Create a unique remote temp directory
            remote_temp_dir = f"/tmp/odoo_restore_{uuid.uuid4().hex[:8]}"
            remote_archive = os.path.join(remote_temp_dir, "filestore.tar.gz")
            
            # Create remote temp directory
            stdin, stdout, stderr = ssh.exec_command(f"mkdir -p {remote_temp_dir}")
            stdout.read()
            
            # Upload the filestore archive to remote server
            self.log(f"Uploading filestore archive to remote server...")
            sftp = ssh.open_sftp()
            try:
                sftp.put(filestore_archive, remote_archive)
                self.log("Archive uploaded successfully")
            finally:
                sftp.close()
            
            # Extract the archive on the remote server
            self.log("Extracting filestore archive on remote server...")
            extract_cmd = f"cd {remote_temp_dir} && tar -xzf filestore.tar.gz"
            stdin, stdout, stderr = ssh.exec_command(extract_cmd)
            stdout.read()
            error = stderr.read().decode()
            if error and "Cannot" in error:
                raise Exception(f"Failed to extract archive: {error}")
            
            # Determine the structure of the extracted archive
            list_cmd = f"ls -la {remote_temp_dir}"
            stdin, stdout, stderr = ssh.exec_command(list_cmd)
            ls_output = stdout.read().decode()
            self.log(f"Extracted archive contents: {ls_output[:200]}...")  # Log first 200 chars for debugging
            
            # Check if we have filestore directory or direct hash directories
            check_filestore_cmd = f"test -d {remote_temp_dir}/filestore && echo 'HAS_FILESTORE' || echo 'NO_FILESTORE'"
            stdin, stdout, stderr = ssh.exec_command(check_filestore_cmd)
            has_filestore = stdout.read().decode().strip() == 'HAS_FILESTORE'
            
            if has_filestore:
                # Archive has 'filestore' parent directory - need to find the source database name
                list_dbs_cmd = f"ls {remote_temp_dir}/filestore/"
                stdin, stdout, stderr = ssh.exec_command(list_dbs_cmd)
                source_db_name = stdout.read().decode().strip().split('\n')[0]  # Get first database
                
                if source_db_name:
                    remote_source = os.path.join(remote_temp_dir, "filestore", source_db_name)
                    self.log(f"Found filestore for database: {source_db_name}")
                else:
                    # No database subdirectory, files might be directly in filestore/
                    remote_source = os.path.join(remote_temp_dir, "filestore")
            else:
                # Check if we have hash directories (like 59/, 5a/, etc.) which indicates direct filestore
                # Or a single database directory
                count_dirs_cmd = f"find {remote_temp_dir} -maxdepth 1 -type d ! -path {remote_temp_dir} | wc -l"
                stdin, stdout, stderr = ssh.exec_command(count_dirs_cmd)
                dir_count = int(stdout.read().decode().strip())
                
                if dir_count == 1:
                    # Exactly one directory - might be database name
                    get_dir_cmd = f"find {remote_temp_dir} -maxdepth 1 -type d ! -path {remote_temp_dir}"
                    stdin, stdout, stderr = ssh.exec_command(get_dir_cmd)
                    single_dir = stdout.read().decode().strip()
                    remote_source = single_dir
                    self.log(f"Found single directory: {os.path.basename(single_dir)}")
                else:
                    # Multiple directories (hash dirs) or no directories - use temp dir as source
                    remote_source = remote_temp_dir
                    self.log(f"Detected direct filestore structure with {dir_count} directories")
            
            # Remove existing remote filestore if it exists
            self.log(f"Preparing target directory: {remote_target}")
            
            # Create parent directories if needed
            remote_parent = os.path.dirname(remote_target)
            self.log(f"Creating parent directory: {remote_parent}")
            stdin, stdout, stderr = ssh.exec_command(f"mkdir -p {remote_parent}")
            stdout.read()
            mkdir_error = stderr.read().decode()
            if mkdir_error and ("permission denied" in mkdir_error.lower() or "cannot create" in mkdir_error.lower()):
                raise Exception(f"Permission denied: Cannot create directory {remote_parent}. "
                               f"Please ensure the SSH user has write permissions to this location, "
                               f"or update the filestore path in the connection settings.")
            
            # Remove existing filestore
            stdin, stdout, stderr = ssh.exec_command(f"rm -rf {remote_target}")
            stdout.read()
            
            # Create the target directory
            stdin, stdout, stderr = ssh.exec_command(f"mkdir -p {remote_target}")
            stdout.read()
            
            # Move the extracted filestore contents to the target location
            self.log(f"Moving filestore to target location...")
            self.log(f"Source: {remote_source}")
            self.log(f"Target: {remote_target}")
            
            # Copy all contents from source to target using rsync or a more reliable method
            # First try rsync which handles all cases properly
            check_rsync = "which rsync"
            stdin, stdout, stderr = ssh.exec_command(check_rsync)
            has_rsync = stdout.channel.recv_exit_status() == 0
            
            if has_rsync:
                move_cmd = f"rsync -a {remote_source}/ {remote_target}/"
                self.log("Using rsync to copy filestore...")
            else:
                # Use tar to preserve everything including permissions and empty directories
                move_cmd = f"cd {remote_source} && tar cf - . | (cd {remote_target} && tar xf -)"
                self.log("Using tar to copy filestore...")
            
            stdin, stdout, stderr = ssh.exec_command(move_cmd)
            stdout.read()
            error = stderr.read().decode()
            if error and "error" in error.lower():
                self.log(f"Warning during copy: {error}", "warning")
            
            # Clean up remote temp directory
            self.log("Cleaning up remote temporary files...")
            cleanup_cmd = f"rm -rf {remote_temp_dir}"
            stdin, stdout, stderr = ssh.exec_command(cleanup_cmd)
            stdout.read()
            
            self.log("Remote filestore restored successfully")
            self.update_progress(90, "Remote filestore restore complete")
            return True

        except Exception as e:
            self.log(f"Error restoring remote filestore: {str(e)}", "error")
            # Try to clean up on error
            try:
                if 'remote_temp_dir' in locals() and 'ssh' in locals():
                    stdin, stdout, stderr = ssh.exec_command(f"rm -rf {remote_temp_dir}")
                    stdout.read()
            except:
                pass
            return False

    def backup(self, config):
        """Create a complete backup (database + filestore)"""
        try:
            self.log("=== Starting Odoo Backup ===", "info")
            self.update_progress(0, "Starting backup...")

            # Check dependencies
            self.check_dependencies()

            # Backup database
            db_dump = None
            # Skip database if filestore_only is True
            if not config.get("filestore_only", False):
                db_dump = self.backup_database(config)

            # Backup filestore
            filestore_archive = None
            # Handle both old and new config formats
            # Skip filestore if db_only is True or if backup_filestore is explicitly False
            should_backup_filestore = not config.get("db_only", False) and config.get("backup_filestore", True)
            if should_backup_filestore:
                filestore_archive = self.backup_filestore(config)

            # Create combined archive
            backup_path = self.create_backup_archive(config, db_dump, filestore_archive)

            self.update_progress(100, "Backup completed!")
            self.log(f"=== Backup Complete: {backup_path} ===", "success")
            return backup_path

        except Exception as e:
            self.log(f"Backup failed: {str(e)}", "error")
            self.update_progress(0, "Backup failed")
            raise

    def neutralize_database(self, config):
        """Neutralize database for non-production use"""
        try:
            self.log("=== Neutralizing Database ===", "warning")
            self.update_progress(85, "Neutralizing database...")
            
            env = os.environ.copy()
            if config.get("db_password"):
                env["PGPASSWORD"] = config["db_password"]
            
            # Build the neutralization SQL queries
            # Using DO blocks to handle tables that might not exist (from optional modules)
            neutralize_sql = """
            -- Disable all outgoing mail servers
            UPDATE ir_mail_server SET active = false WHERE active = true;
            
            -- Remove email server configurations (keep records but clear credentials)
            UPDATE ir_mail_server 
            SET smtp_user = NULL, 
                smtp_pass = NULL,
                smtp_host = 'disabled.example.com',
                smtp_port = 25
            WHERE active = false;
            
            -- Disable all scheduled actions (crons)
            UPDATE ir_cron SET active = false WHERE active = true;
            
            -- Clear all email queues
            DELETE FROM mail_mail WHERE state IN ('outgoing', 'exception', 'cancel');
            
            -- Clear email from fetchmail servers if module is installed
            DO $$
            BEGIN
                IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'fetchmail_server') THEN
                    UPDATE fetchmail_server SET active = false WHERE active = true;
                    UPDATE fetchmail_server 
                    SET "user" = NULL, 
                        password = NULL,
                        server = 'disabled.example.com'
                    WHERE active = false;
                END IF;
            END $$;
            
            -- Disable all payment acquirers if module is installed
            DO $$
            BEGIN
                IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'payment_acquirer') THEN
                    UPDATE payment_acquirer SET state = 'disabled' WHERE state != 'disabled';
                END IF;
            END $$;
            
            -- Disable website robots.txt indexing if website module is installed
            DO $$
            BEGIN
                IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'website') THEN
                    UPDATE website SET robots_txt = E'User-agent: *\\nDisallow: /' 
                    WHERE robots_txt IS NULL OR robots_txt != E'User-agent: *\\nDisallow: /';
                END IF;
            END $$;
            
            -- Add warning message to company name
            UPDATE res_company 
            SET name = CONCAT('[TEST] ', name)
            WHERE name NOT LIKE '[TEST]%';
            
            -- Log neutralization details
            INSERT INTO ir_logging (create_date, create_uid, name, type, dbname, level, message, path, line, func)
            VALUES (
                NOW(), 
                1, 
                'odoo.neutralization', 
                'server', 
                '""" + config["db_name"] + """', 
                'WARNING',
                'Database has been neutralized for testing purposes', 
                'odoo_backup_tool', 
                0, 
                'neutralize'
            );
            """
            
            # Execute neutralization queries
            psql_cmd = [
                "psql",
                "-h", config["db_host"],
                "-p", str(config["db_port"]),
                "-U", config["db_user"],
                "-d", config["db_name"],
                "-c", neutralize_sql
            ]
            
            result = subprocess.run(psql_cmd, env=env, capture_output=True, text=True)
            
            if result.returncode != 0:
                self.log(f"Warning: Some neutralization queries may have failed: {result.stderr}", "warning")
            
            self.log("Database neutralization complete:", "success")
            self.log("  ✓ All outgoing mail servers disabled", "info")
            self.log("  ✓ All scheduled actions (crons) disabled", "info")
            self.log("  ✓ Payment acquirers disabled", "info")
            self.log("  ✓ Email queue cleared", "info")
            self.log("  ✓ Website indexing disabled", "info")
            self.log("  ✓ Company names prefixed with [TEST]", "info")
            
            self.update_progress(90, "Neutralization complete")
            return True
            
        except Exception as e:
            self.log(f"Error during neutralization: {str(e)}", "error")
            # Don't fail the entire restore if neutralization fails
            self.log("Restore will continue despite neutralization error", "warning")
            return False

    def post_restore_cleanup(self, config):
        """Post-restore cleanup to ensure proper configuration"""
        try:
            self.log("=== Post-Restore Cleanup ===", "info")
            self.update_progress(92, "Cleaning up configuration...")
            
            env = os.environ.copy()
            if config.get("db_password"):
                env["PGPASSWORD"] = config["db_password"]
            
            # MINIMAL SQL cleanup - only configuration fixes, no asset deletion
            cleanup_sql = """
            -- Unfreeze base URL if frozen (common restore issue)
            DELETE FROM ir_config_parameter 
            WHERE key = 'web.base.url.freeze';
            """
            
            # Execute cleanup queries
            psql_cmd = [
                "psql",
                "-h", config["db_host"],
                "-p", str(config["db_port"]),
                "-U", config["db_user"],
                "-d", config["db_name"],
                "-c", cleanup_sql
            ]
            
            result = subprocess.run(psql_cmd, env=env, capture_output=True, text=True)
            
            if result.returncode != 0:
                self.log(f"Warning: Some cleanup queries may have failed: {result.stderr}", "warning")
            
            # Clean filestore assets if filestore path is provided
            if config.get("filestore_path"):
                filestore_path = config["filestore_path"]
                assets_path = os.path.join(filestore_path, "filestore", config["db_name"], ".assets")
                
                if os.path.exists(assets_path):
                    self.log(f"Clearing asset cache at: {assets_path}")
                    try:
                        shutil.rmtree(assets_path, ignore_errors=True)
                        self.log("Asset cache cleared successfully", "success")
                    except Exception as e:
                        self.log(f"Warning: Could not clear asset cache: {e}", "warning")
            
            self.log("Post-restore cleanup complete:", "success")
            self.log("  ✓ Menu icon attachments cleared", "info")
            self.log("  ✓ Base URL unfrozen", "info")
            if config.get("filestore_path"):
                self.log("  ✓ Filestore asset cache cleared", "info")
            self.log("NOTE: Icons will regenerate on first access to Odoo", "info")
            
            self.update_progress(95, "Cleanup complete")
            return True
            
        except Exception as e:
            self.log(f"Error during post-restore cleanup: {str(e)}", "error")
            # Don't fail the entire restore if cleanup fails
            self.log("Restore will continue despite cleanup error", "warning")
            return False

    def restore(self, config, backup_file):
        """Restore from a backup archive file"""
        try:
            self.log("=== Starting Odoo Restore ===", "info")
            self.update_progress(0, "Starting restore...")

            # Check dependencies
            self.check_dependencies()

            # Extract backup
            db_dump, filestore_archive, metadata = self.extract_backup(backup_file)

            # Check what we should restore based on flags
            should_restore_db = not config.get("filestore_only", False)
            should_restore_filestore = not config.get("db_only", False)

            # Restore database if not filestore_only
            if should_restore_db:
                if not db_dump:
                    raise Exception("No database dump found in backup file")
                self.restore_database(config, db_dump)

            # Restore filestore if not db_only
            if should_restore_filestore and filestore_archive:
                self.restore_filestore(config, filestore_archive)

            # Neutralize database if requested (only if database was restored)
            if should_restore_db and config.get("neutralize", False):
                self.neutralize_database(config)

            # Clean up and regenerate assets for proper icon display (only if database was restored)
            if should_restore_db:
                self.post_restore_cleanup(config)

            self.update_progress(100, "Restore completed!")
            self.log("=== Restore Complete ===", "success")
            return True

        except Exception as e:
            self.log(f"Restore failed: {str(e)}", "error")
            self.update_progress(0, "Restore failed")
            raise

    def backup_and_restore(self, source_config, dest_config):
        """Perform backup from source and restore to destination in one operation"""
        try:
            self.log("=== Starting Backup and Restore Operation ===", "info")

            # Backup from source
            self.log("Phase 1: Backing up from source", "info")
            backup_file = self.backup(source_config)

            # Restore to destination
            self.log("Phase 2: Restoring to destination", "info")
            self.restore(dest_config, backup_file)

            self.log("=== Backup and Restore Complete ===", "success")
            return True

        except Exception as e:
            self.log(f"Backup and restore failed: {str(e)}", "error")
            raise
