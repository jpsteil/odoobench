"""Docker Export for OdooBench.

Creates self-contained, portable tar.gz archives that include everything
needed to run `docker compose up` and get a working Odoo dev/test instance.
"""

import configparser
import gzip
import json
import os
import shutil
import tarfile
import tempfile
from datetime import datetime

from ..core.backup_restore import OdooBench
from .neutralize_sql import get_neutralize_sql
from .templates import (
    DOCKER_COMPOSE_TEMPLATE,
    DOCKERFILE_TEMPLATE,
    ENTRYPOINT_TEMPLATE,
    ODOO_CONF_TEMPLATE,
    START_ODOO_DOCKER_TEMPLATE,
)


class DockerExporter:
    """Generates a self-contained Docker export tar.gz from an Odoo instance."""

    def __init__(self, progress_callback=None, log_callback=None, conn_manager=None):
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.temp_dir = tempfile.mkdtemp(prefix="odoo_docker_export_")
        self.staging_dir = os.path.join(self.temp_dir, "staging")
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        self.conn_manager = conn_manager
        self.backup_tool = OdooBench(
            progress_callback=self._scaled_progress(5, 55),
            log_callback=log_callback,
            conn_manager=conn_manager,
        )

    def __del__(self):
        """Cleanup temp directory"""
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def log(self, message, level="info"):
        """Log message with callback support"""
        print(message)
        if self.log_callback:
            self.log_callback(message, level)

    def update_progress(self, value, message=""):
        """Update progress with callback support"""
        if self.progress_callback:
            self.progress_callback(value, message)

    def _scaled_progress(self, start, end):
        """Return a progress callback that scales to a sub-range.

        Used to pass to backup_tool so its 0-100 progress maps
        to a slice of our overall progress bar.
        """
        def callback(value, message=""):
            scaled = start + (value / 100.0) * (end - start)
            self.update_progress(scaled, message)
        return callback

    def export(self, source_config, profile):
        """Main export orchestration.

        Args:
            source_config: Odoo connection config dict (same format as backup)
            profile: Docker export profile dict

        Returns:
            Path to the output tar.gz file
        """
        try:
            self.log("=== Starting Docker Export ===", "info")

            # Parse profile JSON fields
            subdirs = json.loads(profile.get("source_subdirs", "[]"))
            extra_files = json.loads(profile.get("extra_files", "[]") or "[]")
            db_name = source_config["db_name"]

            # Step 1: Prepare staging directory
            self.update_progress(0, "Preparing export...")
            self._prepare_staging()

            include_db = profile.get("include_db", 1)
            include_filestore = profile.get("include_filestore", 1)

            # Step 2: Backup database (5-25%)
            if include_db:
                self.update_progress(5, "Backing up database...")
                dump_file = self.backup_tool.backup_database(source_config)

                # Step 3: Compress database dump (25-30%)
                self.update_progress(25, "Compressing database dump...")
                self._compress_database(dump_file)
            else:
                self.update_progress(25, "Skipping database backup...")
                self.log("Database backup skipped (disabled in profile)")

            # Step 4: Backup filestore (30-55%)
            if include_filestore and source_config.get("filestore_path"):
                self.update_progress(30, "Backing up filestore...")
                filestore_archive = self.backup_tool.backup_filestore(source_config)
                if filestore_archive:
                    shutil.copy2(
                        filestore_archive,
                        os.path.join(self.staging_dir, "filestore.tar.gz"),
                    )
            else:
                self.update_progress(55, "Skipping filestore backup...")
                if not include_filestore:
                    self.log("Filestore backup skipped (disabled in profile)")

            # Step 5: Download source tree via SSH (55-75%)
            self.update_progress(55, "Downloading source tree...")
            self._download_source_tree(source_config, profile, subdirs)

            # Step 6: Download pip freeze (75-80%)
            self.update_progress(75, "Capturing Python requirements...")
            self._download_requirements(source_config, profile)

            # Step 7: Download extra files (80-85%)
            self.update_progress(80, "Downloading extra files...")
            self._download_extra_files(source_config, profile, extra_files)

            # Step 8: Generate Docker files (85-90%)
            self.update_progress(85, "Generating Docker configuration...")
            self._generate_docker_files(source_config, profile, subdirs)

            # Step 8b: Generate clone.conf if git clone configured
            git_repo_url = profile.get("git_repo_url", "")
            git_clone_subdir = profile.get("git_clone_subdir", "")
            if git_repo_url and git_clone_subdir:
                self._generate_clone_conf(git_repo_url, git_clone_subdir)

            # Step 9: Generate neutralize.sql (90-92%)
            self.update_progress(90, "Generating neutralization SQL...")
            self._generate_neutralize_sql(profile)

            # Step 10: Generate metadata (92-93%)
            self.update_progress(92, "Writing metadata...")
            self._generate_metadata(source_config, profile, subdirs)

            # Step 11: Create final archive (93-100%)
            self.update_progress(93, "Creating export archive...")
            output_path = self._create_export_archive(source_config, profile)

            self.update_progress(100, "Docker export complete!")
            self.log(f"Docker export saved to: {output_path}", "success")
            self.log("=== Docker Export Complete ===", "success")
            self.log("")
            self.log("--- Next Steps ---")
            archive_name = os.path.basename(output_path)
            self.log(f"  1. Extract the startup script from the archive:")
            self.log(f"       tar xzf {archive_name} start_odoo_docker.sh")
            self.log(f"       mv start_odoo_docker.sh ~/scripts/")
            self.log(f"       chmod +x ~/scripts/start_odoo_docker.sh")
            self.log(f"  2. Run it:")
            self.log(f"       ~/scripts/start_odoo_docker.sh")
            self.log("")
            self.log("  On first run it will extract the archive, build containers,")
            self.log("  and start Odoo. Subsequent runs auto-detect git-changed")
            self.log("  modules and upgrade them.")
            self.log("")
            self.log("  Other modes:")
            self.log("    --fresh [archive]   Tear down, re-extract, rebuild")
            self.log("    --all               Upgrade all installed repo modules")
            self.log("    -u module_name      Upgrade a specific module")
            return output_path

        except Exception as e:
            self.log(f"Error during Docker export: {e}", "error")
            raise

    def _prepare_staging(self):
        """Create staging directory structure"""
        os.makedirs(self.staging_dir, exist_ok=True)
        os.makedirs(os.path.join(self.staging_dir, "init"), exist_ok=True)
        os.makedirs(os.path.join(self.staging_dir, "qlf"), exist_ok=True)

    def _compress_database(self, dump_file):
        """Compress the SQL dump to .sql.gz and place in staging/init/"""
        output = os.path.join(self.staging_dir, "init", "database.sql.gz")
        with open(dump_file, "rb") as f_in:
            with gzip.open(output, "wb", compresslevel=6) as f_out:
                shutil.copyfileobj(f_in, f_out)
        self.log("Database dump compressed")

    def _is_local(self, source_config):
        """Check if source is local (no SSH needed)"""
        return source_config.get("is_local", False)

    def _get_ssh_client(self, source_config):
        """Get SSH client for the source connection"""
        return self.backup_tool._get_ssh_client({
            'host': source_config.get('host'),
            'port': source_config.get('ssh_port', 22),
            'username': source_config.get('ssh_username'),
            'password': source_config.get('ssh_password'),
            'key_path': source_config.get('ssh_key_path'),
        })

    def _download_source_tree(self, source_config, profile, subdirs):
        """Copy/download source directories into staging"""
        if self._is_local(source_config):
            self._copy_local_source_tree(profile, subdirs)
        else:
            self._download_remote_source_tree(source_config, profile, subdirs)

    def _copy_local_source_tree(self, profile, subdirs):
        """Copy source directories from local filesystem"""
        source_base = profile.get("source_base_dir", "")
        dest_base = os.path.join(self.staging_dir, "qlf")
        git_clone_subdir = profile.get("git_clone_subdir", "")

        copied = []
        for subdir in subdirs:
            if git_clone_subdir and subdir == git_clone_subdir:
                self.log(f"Skipping {subdir} (will be git cloned at runtime)")
                continue
            src = os.path.join(source_base, subdir)
            dst = os.path.join(dest_base, subdir)
            if os.path.exists(src):
                self.log(f"Copying {src}...")
                shutil.copytree(src, dst, symlinks=True)
                copied.append(subdir)
            else:
                self.log(f"Warning: Source directory not found: {src}", "warning")

        self.log(f"Source tree copied: {', '.join(copied)}")

    def _download_remote_source_tree(self, source_config, profile, subdirs):
        """Download source directories from remote server via SSH"""
        ssh = self._get_ssh_client(source_config)

        try:
            source_base = profile.get("source_base_dir", "")
            git_clone_subdir = profile.get("git_clone_subdir", "")
            copy_subdirs = [s for s in subdirs if s != git_clone_subdir]
            if git_clone_subdir:
                self.log(f"Skipping {git_clone_subdir} (will be git cloned at runtime)")
            subdirs_str = " ".join(copy_subdirs)
            remote_temp = f"/tmp/qlf_source_{self.timestamp}.tar.gz"

            self.log(f"Creating remote archive of {source_base}/({subdirs_str})...")

            tar_cmd = (
                f"cd '{source_base}' && tar -czf '{remote_temp}' {subdirs_str}"
            )
            stdin, stdout, stderr = ssh.exec_command(tar_cmd)
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                err = stderr.read().decode()
                raise RuntimeError(
                    f"Failed to create remote source archive: {err}"
                )

            local_archive = os.path.join(self.temp_dir, "qlf_source.tar.gz")
            self.log("Downloading source tree...")
            sftp = ssh.open_sftp()
            sftp.get(remote_temp, local_archive)
            sftp.close()

            self.log("Extracting source tree...")
            with tarfile.open(local_archive, "r:gz") as tar:
                tar.extractall(path=os.path.join(self.staging_dir, "qlf"))

            ssh.exec_command(f"rm -f '{remote_temp}'")
            self.log(f"Source tree downloaded: {subdirs_str}")

        finally:
            ssh.close()

    def _download_requirements(self, source_config, profile):
        """Capture pip freeze from venv (local or remote)"""
        if self._is_local(source_config):
            self._capture_local_requirements(profile)
        else:
            self._capture_remote_requirements(source_config, profile)

    def _capture_local_requirements(self, profile):
        """Capture pip freeze from local venv"""
        import subprocess

        venv_path = profile.get("venv_path", "")
        pip_path = os.path.join(venv_path, "bin", "pip") if venv_path else ""

        output_file = os.path.join(self.staging_dir, "requirements.txt")

        if venv_path and os.path.exists(pip_path):
            self.log(f"Running pip freeze on local venv: {venv_path}...")
            try:
                result = subprocess.run(
                    [pip_path, "freeze"],
                    capture_output=True, text=True, check=True,
                )
                with open(output_file, "w") as f:
                    f.write(result.stdout)
                self.log("Python requirements captured")
            except subprocess.CalledProcessError as e:
                self.log(f"Warning: pip freeze failed: {e.stderr}", "warning")
                with open(output_file, "w") as f:
                    f.write("# pip freeze failed\n")
        else:
            self.log(
                f"Warning: venv not found at {venv_path}", "warning"
            )
            with open(output_file, "w") as f:
                f.write(f"# venv not found at {venv_path}\n")

    def _capture_remote_requirements(self, source_config, profile):
        """Capture pip freeze from remote venv via SSH"""
        ssh = self._get_ssh_client(source_config)

        try:
            venv_path = profile.get("venv_path", "")
            pip_cmd = f"'{venv_path}/bin/pip' freeze"

            self.log(f"Running pip freeze on remote venv: {venv_path}...")
            stdin, stdout, stderr = ssh.exec_command(pip_cmd)
            exit_status = stdout.channel.recv_exit_status()

            if exit_status != 0:
                err = stderr.read().decode()
                self.log(
                    f"Warning: pip freeze failed: {err}. "
                    "You may need to manually create requirements.txt.",
                    "warning",
                )
                requirements = (
                    "# pip freeze failed on source server\n"
                    "# You may need to populate this manually\n"
                )
            else:
                requirements = stdout.read().decode()

            output = os.path.join(self.staging_dir, "requirements.txt")
            with open(output, "w") as f:
                f.write(requirements)
            self.log("Python requirements captured")

        finally:
            ssh.close()

    def _download_extra_files(self, source_config, profile, extra_files):
        """Copy/download extra files (e.g., full_update.sh)"""
        if not extra_files:
            return

        if self._is_local(source_config):
            self._copy_local_extra_files(profile, extra_files)
        else:
            self._download_remote_extra_files(source_config, profile, extra_files)

    def _copy_local_extra_files(self, profile, extra_files):
        """Copy extra files from local filesystem"""
        source_base = profile.get("source_base_dir", "")

        for filename in extra_files:
            if os.path.isabs(filename):
                src = filename
            else:
                # Try relative to source base dir first, then home
                src = os.path.join(source_base, filename)
                if not os.path.exists(src):
                    src = os.path.expanduser(f"~/{filename}")

            dst = os.path.join(self.staging_dir, os.path.basename(filename))

            if os.path.exists(src):
                self.log(f"Copying {src}...")
                shutil.copy2(src, dst)
            else:
                self.log(f"Warning: Extra file not found: {src}", "warning")

    def _download_remote_extra_files(self, source_config, profile, extra_files):
        """Download extra files from remote server via SSH"""
        ssh = self._get_ssh_client(source_config)
        source_base = profile.get("source_base_dir", "")

        try:
            sftp = ssh.open_sftp()

            for filename in extra_files:
                if os.path.isabs(filename):
                    remote_path = filename
                else:
                    remote_path = os.path.join(source_base, filename)

                local_path = os.path.join(
                    self.staging_dir, os.path.basename(filename)
                )

                try:
                    self.log(f"Downloading {remote_path}...")
                    sftp.get(remote_path, local_path)
                except FileNotFoundError:
                    self.log(
                        f"Warning: Extra file not found: {remote_path}",
                        "warning",
                    )

            sftp.close()
        finally:
            ssh.close()

    def _generate_docker_files(self, source_config, profile, subdirs):
        """Generate Dockerfile, docker-compose.yml, entrypoint.sh, odoo.conf"""
        db_name = source_config["db_name"]
        container_base = profile.get("container_base_dir", "/opt/odoo/qlf")

        # Build addons_path by reading the prod odoo.conf from downloaded source
        addons_path = self._build_addons_path(profile, subdirs, container_base)

        # Build COPY lines only for extra files that were actually downloaded
        extra_files = json.loads(profile.get("extra_files", "[]") or "[]")
        copy_lines = ""
        for f in extra_files:
            basename = os.path.basename(f)
            if os.path.exists(os.path.join(self.staging_dir, basename)):
                copy_lines += f"COPY {basename} /opt/odoo/{basename}\n"

        # Generate docker-compose.yml
        compose = DOCKER_COMPOSE_TEMPLATE.substitute(
            postgres_version=profile.get("postgres_version", "16"),
            odoo_port=profile.get("odoo_port", 8069),
            longpolling_port=profile.get("odoo_port", 8069) + 3,
            db_name=db_name,
            mailpit_http_port=profile.get("mailpit_http_port", 8025),
        )
        self._write_staging_file("docker-compose.yml", compose)

        # Generate Dockerfile
        dockerfile = DOCKERFILE_TEMPLATE.substitute(
            python_version=profile.get("python_version", "3.12"),
            copy_extra_files=copy_lines,
        )
        self._write_staging_file("Dockerfile", dockerfile)

        # Generate entrypoint.sh - find the Odoo base subdir (contains odoo-bin)
        odoo_subdir = "odoo"
        for subdir in subdirs:
            if subdir.startswith("odoo"):
                odoo_subdir = subdir
                break
        entrypoint = ENTRYPOINT_TEMPLATE.substitute(
            db_name=db_name, odoo_subdir=odoo_subdir
        )
        self._write_staging_file("entrypoint.sh", entrypoint)

        # Generate odoo.conf
        odoo_conf = ODOO_CONF_TEMPLATE.substitute(
            addons_path=addons_path,
            db_name=db_name,
        )
        self._write_staging_file("odoo.conf", odoo_conf)

        # Generate start_odoo_docker.sh (host-side orchestration script)
        repo_subdir = profile.get("git_clone_subdir", "").strip()
        if not repo_subdir:
            # Fall back to first non-odoo subdir (likely the custom modules repo)
            for subdir in subdirs:
                if not subdir.startswith("odoo"):
                    repo_subdir = subdir
                    break
            if not repo_subdir:
                repo_subdir = subdirs[0] if subdirs else "odoo"
        start_script = START_ODOO_DOCKER_TEMPLATE.substitute(
            repo_subdir=repo_subdir,
        )
        self._write_staging_file("start_odoo_docker.sh", start_script)

        self.log("Docker configuration files generated")

    def _build_addons_path(self, profile, subdirs, container_base):
        """Build the addons_path for the container odoo.conf.

        Reads the prod odoo.conf from the downloaded source tree, remaps
        each path from prod layout to container layout.
        """
        odoo_conf_rel = profile.get("odoo_conf_path", "odoo/odoo.conf")
        local_conf = os.path.join(self.staging_dir, "qlf", odoo_conf_rel)

        if os.path.exists(local_conf):
            config = configparser.ConfigParser()
            config.read(local_conf)
            if "options" in config:
                prod_addons = config["options"].get("addons_path", "")
                if prod_addons:
                    conf_dir = os.path.join(
                        profile.get("source_base_dir", ""),
                        os.path.dirname(odoo_conf_rel),
                    )
                    return self._remap_addons_path(
                        prod_addons,
                        profile.get("source_base_dir", ""),
                        container_base,
                        conf_dir,
                    )

        # Fallback: build from subdirs
        self.log(
            "Could not read addons_path from prod odoo.conf, building from subdirs",
            "warning",
        )
        paths = []
        for subdir in subdirs:
            if subdir.startswith("odoo"):
                # Odoo base: addons are in odoo/addons inside the subdir
                paths.append(f"{container_base}/{subdir}/odoo/addons")
            else:
                paths.append(f"{container_base}/{subdir}")
        return ",".join(paths)

    def _remap_addons_path(self, prod_addons_path, source_base_dir, container_base, conf_dir):
        """Remap production addons_path to container paths.

        Handles both absolute paths and relative paths (resolved against
        the directory containing odoo.conf).

        Example: /home/administrator/qlf/odoo/addons -> /opt/odoo/qlf/odoo/addons
        Example: ../qlf-odoo -> resolved via conf_dir -> /opt/odoo/qlf/qlf-odoo
        """
        paths = []
        for path in prod_addons_path.split(","):
            path = path.strip()
            if not path:
                continue
            # Resolve relative paths against the odoo.conf directory
            if not os.path.isabs(path):
                path = os.path.normpath(os.path.join(conf_dir, path))
            # Try to make relative to source_base_dir
            if path.startswith(source_base_dir):
                relative = path[len(source_base_dir):].lstrip("/")
                paths.append(f"{container_base}/{relative}")
            else:
                self.log(
                    f"Skipping unmapped addons path: {path}", "warning"
                )
        return ",".join(paths)

    def _generate_clone_conf(self, repo_url, subdir):
        """Write clone.conf so the start script knows what to git clone"""
        conf_path = os.path.join(self.staging_dir, "clone.conf")
        with open(conf_path, "w") as f:
            f.write(f"repo_url={repo_url}\n")
            f.write(f"subdir={subdir}\n")
        self.log(f"Git clone config written: {subdir} from {repo_url}")

    def _generate_neutralize_sql(self, profile):
        """Generate neutralize.sql file"""
        custom_sql = profile.get("custom_neutralize_sql", "")
        sql = get_neutralize_sql(custom_sql=custom_sql)
        self._write_staging_file("neutralize.sql", sql)
        self.log("Neutralization SQL generated")

    def _generate_metadata(self, source_config, profile, subdirs):
        """Generate metadata.json"""
        metadata = {
            "type": "docker_export",
            "timestamp": self.timestamp,
            "db_name": source_config["db_name"],
            "odoo_version": source_config.get("odoo_version", "17.0"),
            "source_subdirs": subdirs,
            "postgres_version": profile.get("postgres_version", "16"),
            "python_version": profile.get("python_version", "3.12"),
            "has_filestore": os.path.exists(
                os.path.join(self.staging_dir, "filestore.tar.gz")
            ),
            "tool_version": "1.0.0",
        }
        self._write_staging_file("metadata.json", json.dumps(metadata, indent=2))

    def _create_export_archive(self, source_config, profile):
        """Create the final tar.gz archive from the staging directory"""
        db_name = source_config["db_name"].upper()
        output_dir = profile.get(
            "output_dir",
            os.path.expanduser("~/Documents/OdooBackups"),
        )
        os.makedirs(output_dir, exist_ok=True)

        filename = f"backup_{db_name}_{self.timestamp}_docker.tar.gz"
        output_path = os.path.join(output_dir, filename)

        self.log(f"Creating archive: {filename}...")

        with tarfile.open(output_path, "w:gz") as tar:
            for item in os.listdir(self.staging_dir):
                item_path = os.path.join(self.staging_dir, item)
                # Set execute permission on shell scripts
                if item.endswith(".sh"):
                    info = tar.gettarinfo(item_path, arcname=item)
                    info.mode = 0o755
                    with open(item_path, "rb") as f:
                        tar.addfile(info, f)
                else:
                    tar.add(item_path, arcname=item)

        archive_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        self.log(f"Archive created: {archive_size_mb:.1f} MB")

        return output_path

    def _write_staging_file(self, filename, content):
        """Write a file into the staging directory"""
        path = os.path.join(self.staging_dir, filename)
        with open(path, "w") as f:
            f.write(content)
