"""Connection dialog for adding/editing Odoo connections."""

import os
import configparser
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QPushButton, QSpinBox, QCheckBox, QComboBox,
    QFileDialog, QDialogButtonBox, QLabel, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt


class ConnectionDialog(QDialog):
    """Dialog for creating/editing Odoo connections."""

    def __init__(self, parent=None, instance_manager=None, instance: dict = None):
        super().__init__(parent)
        self.instance_manager = instance_manager
        self.instance = instance
        self.is_edit = instance is not None
        self.result = None

        self.setWindowTitle("Edit Connection" if self.is_edit else "New Connection")
        self.setMinimumWidth(500)
        self.setModal(True)
        self._setup_ui()

        if self.is_edit:
            self._load_instance()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Load from odoo.conf button
        load_btn = QPushButton("Load from odoo.conf")
        load_btn.clicked.connect(self._load_from_conf)
        layout.addWidget(load_btn)

        # Connection Details group
        details_group = QGroupBox("Connection Details")
        details_layout = QFormLayout(details_group)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("My Odoo Server")
        details_layout.addRow("Connection Name:", self.name_edit)

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("localhost")
        details_layout.addRow("Database Host:", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(5432)
        details_layout.addRow("Database Port:", self.port_spin)

        self.database_edit = QLineEdit()
        self.database_edit.setPlaceholderText("odoo")
        details_layout.addRow("Database Name:", self.database_edit)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("odoo")
        details_layout.addRow("Username:", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        details_layout.addRow("DB Password:", self.password_edit)

        # Odoo web login (for sync operations)
        self.odoo_user_edit = QLineEdit()
        self.odoo_user_edit.setPlaceholderText("admin (for sync)")
        details_layout.addRow("Odoo User:", self.odoo_user_edit)

        self.odoo_password_edit = QLineEdit()
        self.odoo_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.odoo_password_edit.setPlaceholderText("Odoo web login password")
        details_layout.addRow("Odoo Password:", self.odoo_password_edit)

        # Filestore path with browse
        filestore_layout = QHBoxLayout()
        self.filestore_edit = QLineEdit()
        self.filestore_edit.setPlaceholderText("/var/lib/odoo or ~/.local/share/Odoo")
        filestore_layout.addWidget(self.filestore_edit)
        self.filestore_browse_btn = QPushButton("Browse...")
        self.filestore_browse_btn.clicked.connect(self._browse_filestore)
        filestore_layout.addWidget(self.filestore_browse_btn)
        details_layout.addRow("Filestore Path:", filestore_layout)

        # Log path
        self.log_path_edit = QLineEdit()
        self.log_path_edit.setPlaceholderText("/var/log/odoo/odoo-server.log")
        details_layout.addRow("Log Path:", self.log_path_edit)

        self.version_combo = QComboBox()
        self.version_combo.addItems(["18.0", "17.0", "16.0", "15.0", "14.0", "13.0", "12.0"])
        self.version_combo.setCurrentText("17.0")
        details_layout.addRow("Odoo Version:", self.version_combo)

        self.is_local_check = QCheckBox("Local Development Connection")
        details_layout.addRow("", self.is_local_check)

        self.allow_restore_check = QCheckBox("Allow Restore Operations")
        self.allow_restore_check.setToolTip("Be careful with production databases!")
        details_layout.addRow("", self.allow_restore_check)

        self.allow_sync_check = QCheckBox("Allow Sync Operations (Target)")
        self.allow_sync_check.setToolTip("Allow this connection to be a sync target. Use for dev/test databases only!")
        details_layout.addRow("", self.allow_sync_check)

        layout.addWidget(details_group)

        # SSH group
        ssh_group = QGroupBox("Remote Server Access (SSH)")
        ssh_layout = QFormLayout(ssh_group)

        self.use_ssh_check = QCheckBox("Use SSH for remote server access")
        self.use_ssh_check.toggled.connect(self._toggle_ssh)
        ssh_layout.addRow("", self.use_ssh_check)

        self.ssh_host_edit = QLineEdit()
        self.ssh_host_edit.setPlaceholderText("server.example.com")
        self.ssh_host_edit.setEnabled(False)
        ssh_layout.addRow("SSH Host:", self.ssh_host_edit)

        self.ssh_port_spin = QSpinBox()
        self.ssh_port_spin.setRange(1, 65535)
        self.ssh_port_spin.setValue(22)
        self.ssh_port_spin.setEnabled(False)
        ssh_layout.addRow("SSH Port:", self.ssh_port_spin)

        self.ssh_username_edit = QLineEdit()
        self.ssh_username_edit.setPlaceholderText("administrator")
        self.ssh_username_edit.setEnabled(False)
        ssh_layout.addRow("SSH Username:", self.ssh_username_edit)

        self.ssh_password_edit = QLineEdit()
        self.ssh_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ssh_password_edit.setEnabled(False)
        ssh_layout.addRow("SSH Password:", self.ssh_password_edit)

        # SSH key path
        ssh_key_layout = QHBoxLayout()
        self.ssh_key_edit = QLineEdit()
        self.ssh_key_edit.setPlaceholderText("~/.ssh/id_rsa (optional)")
        self.ssh_key_edit.setEnabled(False)
        ssh_key_layout.addWidget(self.ssh_key_edit)
        self.ssh_key_browse_btn = QPushButton("Browse...")
        self.ssh_key_browse_btn.clicked.connect(self._browse_ssh_key)
        self.ssh_key_browse_btn.setEnabled(False)
        ssh_key_layout.addWidget(self.ssh_key_browse_btn)
        ssh_layout.addRow("SSH Key:", ssh_key_layout)

        layout.addWidget(ssh_group)

        # PostgreSQL Server SSH group (for running pg_dump on PG server)
        pg_ssh_group = QGroupBox("PostgreSQL Server SSH (Optional)")
        pg_ssh_group.setToolTip("If PG is on a separate server, configure SSH here to run pg_dump directly on it")
        pg_ssh_layout = QFormLayout(pg_ssh_group)

        self.pg_ssh_host_edit = QLineEdit()
        self.pg_ssh_host_edit.setPlaceholderText("Leave empty to use Odoo server SSH")
        pg_ssh_layout.addRow("PG SSH Host:", self.pg_ssh_host_edit)

        self.pg_ssh_port_spin = QSpinBox()
        self.pg_ssh_port_spin.setRange(1, 65535)
        self.pg_ssh_port_spin.setValue(22)
        pg_ssh_layout.addRow("PG SSH Port:", self.pg_ssh_port_spin)

        self.pg_ssh_username_edit = QLineEdit()
        self.pg_ssh_username_edit.setPlaceholderText("administrator")
        pg_ssh_layout.addRow("PG SSH Username:", self.pg_ssh_username_edit)

        self.pg_ssh_password_edit = QLineEdit()
        self.pg_ssh_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        pg_ssh_layout.addRow("PG SSH Password:", self.pg_ssh_password_edit)

        # PG SSH key path
        pg_ssh_key_layout = QHBoxLayout()
        self.pg_ssh_key_edit = QLineEdit()
        self.pg_ssh_key_edit.setPlaceholderText("~/.ssh/id_rsa")
        pg_ssh_key_layout.addWidget(self.pg_ssh_key_edit)
        pg_ssh_key_browse_btn = QPushButton("Browse...")
        pg_ssh_key_browse_btn.clicked.connect(self._browse_pg_ssh_key)
        pg_ssh_key_layout.addWidget(pg_ssh_key_browse_btn)
        pg_ssh_layout.addRow("PG SSH Key:", pg_ssh_key_layout)

        layout.addWidget(pg_ssh_group)

        # Group/Notes group
        meta_group = QGroupBox("Organization")
        meta_layout = QFormLayout(meta_group)

        self.group_edit = QLineEdit()
        self.group_edit.setPlaceholderText("Production, Development, etc.")
        meta_layout.addRow("Group:", self.group_edit)

        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Optional notes...")
        meta_layout.addRow("Notes:", self.notes_edit)

        layout.addWidget(meta_group)

        # Dialog buttons
        button_layout = QHBoxLayout()

        test_btn = QPushButton("Test Connection")
        test_btn.clicked.connect(self._test_connection)
        button_layout.addWidget(test_btn)

        button_layout.addStretch()

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._save)
        button_box.rejected.connect(self.reject)
        button_layout.addWidget(button_box)

        layout.addLayout(button_layout)

    def _toggle_ssh(self, enabled: bool):
        """Enable/disable SSH fields."""
        self.ssh_host_edit.setEnabled(enabled)
        self.ssh_port_spin.setEnabled(enabled)
        self.ssh_username_edit.setEnabled(enabled)
        self.ssh_password_edit.setEnabled(enabled)
        self.ssh_key_edit.setEnabled(enabled)
        self.ssh_key_browse_btn.setEnabled(enabled)
        # Disable local filestore browse when SSH enabled
        self.filestore_browse_btn.setEnabled(not enabled)

    def _browse_filestore(self):
        """Browse for filestore directory."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Filestore Directory",
            self.filestore_edit.text() or os.path.expanduser("~")
        )
        if directory:
            self.filestore_edit.setText(directory)

    def _browse_ssh_key(self):
        """Browse for SSH key file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select SSH Key",
            os.path.expanduser("~/.ssh"),
            "All Files (*)"
        )
        if filepath:
            self.ssh_key_edit.setText(filepath)

    def _browse_pg_ssh_key(self):
        """Browse for PG SSH key file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select PG SSH Key",
            os.path.expanduser("~/.ssh"),
            "All Files (*)"
        )
        if filepath:
            self.pg_ssh_key_edit.setText(filepath)

    def _load_from_conf(self):
        """Load configuration from odoo.conf file."""
        if self.use_ssh_check.isChecked():
            self._load_from_remote_conf()
        else:
            self._load_from_local_conf()

    def _load_from_local_conf(self):
        """Load configuration from local odoo.conf file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select Odoo Configuration File",
            os.path.expanduser("~"),
            "Config Files (*.conf);;All Files (*)"
        )
        if not filepath:
            return

        try:
            config = configparser.ConfigParser()
            config.read(filepath)
            self._apply_conf_options(config)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load configuration: {e}")

    def _load_from_remote_conf(self):
        """Load configuration from remote odoo.conf via SSH."""
        from PyQt6.QtWidgets import QInputDialog

        # Validate SSH settings
        ssh_host = self.ssh_host_edit.text().strip()
        ssh_user = self.ssh_username_edit.text().strip()
        if not ssh_host or not ssh_user:
            QMessageBox.warning(self, "SSH Required",
                "Please fill in SSH Host and Username first")
            return

        # Ask for remote path
        remote_path, ok = QInputDialog.getText(
            self, "Remote Config Path",
            "Enter the path to odoo.conf on the remote server:",
            text="/etc/odoo/odoo.conf"
        )
        if not ok or not remote_path:
            return

        try:
            import paramiko
            import io

            # Connect via SSH
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs = {
                'hostname': ssh_host,
                'port': self.ssh_port_spin.value(),
                'username': ssh_user,
            }

            ssh_password = self.ssh_password_edit.text()
            ssh_key = self.ssh_key_edit.text().strip()

            if ssh_key and os.path.exists(os.path.expanduser(ssh_key)):
                connect_kwargs['key_filename'] = os.path.expanduser(ssh_key)
            elif ssh_password:
                connect_kwargs['password'] = ssh_password

            ssh.connect(**connect_kwargs)

            # Read the remote file
            stdin, stdout, stderr = ssh.exec_command(f"cat '{remote_path}'")
            content = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            ssh.close()

            if not content and error:
                raise Exception(error)

            # Parse the config
            config = configparser.ConfigParser()
            config.read_string(content)
            self._apply_conf_options(config)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load remote configuration: {e}")

    def _apply_conf_options(self, config):
        """Apply parsed config options to form fields."""
        if 'options' not in config:
            QMessageBox.warning(self, "Invalid File", "No 'options' section found in config file")
            return

        options = config['options']

        if 'db_host' in options:
            self.host_edit.setText(options['db_host'])
        if 'db_port' in options:
            self.port_spin.setValue(int(options['db_port']))
        if 'db_name' in options:
            self.database_edit.setText(options['db_name'])
        if 'db_user' in options:
            self.username_edit.setText(options['db_user'])
        if 'db_password' in options:
            self.password_edit.setText(options['db_password'])
        if 'data_dir' in options:
            self.filestore_edit.setText(options['data_dir'])
        if 'logfile' in options:
            self.log_path_edit.setText(options['logfile'])

        QMessageBox.information(self, "Success", "Configuration loaded from odoo.conf")

    def _load_instance(self):
        """Load existing instance data into form."""
        if not self.instance:
            return

        self.name_edit.setText(self.instance.get('name') or '')
        self.host_edit.setText(self.instance.get('db_host') or '')
        self.port_spin.setValue(self.instance.get('db_port') or 5432)
        self.database_edit.setText(self.instance.get('db_name') or '')
        self.username_edit.setText(self.instance.get('db_user') or '')
        self.password_edit.setText(self.instance.get('db_password') or '')
        self.odoo_user_edit.setText(self.instance.get('odoo_user') or '')
        self.odoo_password_edit.setText(self.instance.get('odoo_password') or '')
        self.filestore_edit.setText(self.instance.get('filestore_path') or '')
        self.log_path_edit.setText(self.instance.get('log_path') or '')
        self.version_combo.setCurrentText(self.instance.get('odoo_version') or '17.0')
        self.is_local_check.setChecked(bool(self.instance.get('is_local')))
        self.allow_restore_check.setChecked(bool(self.instance.get('allow_restore')))
        self.allow_sync_check.setChecked(bool(self.instance.get('allow_sync')))
        self.group_edit.setText(self.instance.get('group_name') or '')
        self.notes_edit.setText(self.instance.get('notes') or '')

        # SSH settings
        if self.instance.get('host') and self.instance.get('ssh_username'):
            self.use_ssh_check.setChecked(True)
            self.ssh_host_edit.setText(self.instance.get('host') or '')
            self.ssh_port_spin.setValue(self.instance.get('ssh_port') or 22)
            self.ssh_username_edit.setText(self.instance.get('ssh_username') or '')
            self.ssh_password_edit.setText(self.instance.get('ssh_password') or '')
            self.ssh_key_edit.setText(self.instance.get('ssh_key_path') or '')

        # PG SSH settings
        self.pg_ssh_host_edit.setText(self.instance.get('pg_ssh_host') or '')
        self.pg_ssh_port_spin.setValue(self.instance.get('pg_ssh_port') or 22)
        self.pg_ssh_username_edit.setText(self.instance.get('pg_ssh_username') or '')
        self.pg_ssh_password_edit.setText(self.instance.get('pg_ssh_password') or '')
        self.pg_ssh_key_edit.setText(self.instance.get('pg_ssh_key_path') or '')

    def _test_connection(self):
        """Test the database connection."""
        from ...core.backup_restore import OdooBench

        config = self._get_config()
        if not config:
            return

        try:
            bench = OdooBench(conn_manager=self.instance_manager)
            success, message = bench.test_connection(config)

            if success:
                QMessageBox.information(self, "Connection Test", message)
            else:
                QMessageBox.warning(self, "Connection Test", message)

        except Exception as e:
            QMessageBox.critical(self, "Connection Error", str(e))

    def _validate(self) -> bool:
        """Validate form fields."""
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Validation Error", "Connection name is required")
            self.name_edit.setFocus()
            return False

        if not self.host_edit.text().strip():
            QMessageBox.warning(self, "Validation Error", "Database host is required")
            self.host_edit.setFocus()
            return False

        if not self.database_edit.text().strip():
            QMessageBox.warning(self, "Validation Error", "Database name is required")
            self.database_edit.setFocus()
            return False

        if not self.username_edit.text().strip():
            QMessageBox.warning(self, "Validation Error", "Username is required")
            self.username_edit.setFocus()
            return False

        if self.use_ssh_check.isChecked():
            if not self.ssh_host_edit.text().strip():
                QMessageBox.warning(self, "Validation Error", "SSH host is required when SSH is enabled")
                self.ssh_host_edit.setFocus()
                return False
            if not self.ssh_username_edit.text().strip():
                QMessageBox.warning(self, "Validation Error", "SSH username is required when SSH is enabled")
                self.ssh_username_edit.setFocus()
                return False

        return True

    def _get_config(self) -> dict:
        """Get current form values as config dict."""
        config = {
            'name': self.name_edit.text().strip(),
            'db_host': self.host_edit.text().strip(),
            'db_port': self.port_spin.value(),
            'db_name': self.database_edit.text().strip(),
            'db_user': self.username_edit.text().strip(),
            'db_password': self.password_edit.text(),
            'odoo_user': self.odoo_user_edit.text().strip(),
            'odoo_password': self.odoo_password_edit.text(),
            'filestore_path': self.filestore_edit.text().strip(),
            'log_path': self.log_path_edit.text().strip(),
            'odoo_version': self.version_combo.currentText(),
            'is_local': self.is_local_check.isChecked(),
            'allow_restore': self.allow_restore_check.isChecked(),
            'allow_sync': self.allow_sync_check.isChecked(),
            'group_name': self.group_edit.text().strip() or 'Default',
            'notes': self.notes_edit.text().strip(),
        }

        if self.use_ssh_check.isChecked():
            config['host'] = self.ssh_host_edit.text().strip()
            config['ssh_port'] = self.ssh_port_spin.value()
            config['ssh_username'] = self.ssh_username_edit.text().strip()
            config['ssh_password'] = self.ssh_password_edit.text()
            config['ssh_key_path'] = self.ssh_key_edit.text().strip()
        else:
            config['host'] = 'localhost'
            config['ssh_port'] = 22
            config['ssh_username'] = ''
            config['ssh_password'] = ''
            config['ssh_key_path'] = ''

        # PG SSH settings (optional, for running pg_dump on PG server)
        config['pg_ssh_host'] = self.pg_ssh_host_edit.text().strip()
        config['pg_ssh_port'] = self.pg_ssh_port_spin.value() if self.pg_ssh_host_edit.text().strip() else None
        config['pg_ssh_username'] = self.pg_ssh_username_edit.text().strip()
        config['pg_ssh_password'] = self.pg_ssh_password_edit.text()
        config['pg_ssh_key_path'] = self.pg_ssh_key_edit.text().strip()

        return config

    def _save(self):
        """Save the connection."""
        if not self._validate():
            return

        config = self._get_config()
        name = config.pop('name')

        try:
            if self.is_edit:
                self.instance_manager.update_instance(self.instance['id'], name, config)
            else:
                self.instance_manager.save_instance(name, config)

            self.result = name
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save connection: {e}")
