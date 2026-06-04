"""Main window for OdooBench Qt GUI."""

import os
import json
import threading
from typing import Optional, Dict, Any, List

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QTabWidget, QFrame, QLabel,
    QPushButton, QStatusBar, QMenu, QMenuBar, QMessageBox,
    QFileDialog, QApplication, QLineEdit, QComboBox, QCheckBox,
    QTextEdit, QProgressBar, QGroupBox, QFormLayout, QSpinBox,
    QListWidget, QListWidgetItem, QHeaderView, QTableWidget,
    QTableWidgetItem, QAbstractItemView
)
from PyQt6.QtCore import Qt, QSettings, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QAction, QKeySequence, QFont, QCloseEvent, QColor

from ..db.odoo_connection_manager import OdooInstanceManager
from ..core.executor import create_executor
from ..core.backup_restore import OdooBench
from ..version import __version__

from .widgets.log_viewer import LogViewer
from .widgets.progress_widget import ProgressWidget
from .dialogs.connection_dialog import ConnectionDialog
from .dialogs.settings_dialog import SettingsDialog
from .dialogs.docker_export_dialog import DockerExportProfileDialog
from .dialogs.about_dialog import AboutDialog
from .dialogs.sync_dialog import SyncDialog


class WorkerSignals(QObject):
    """Signals for background worker threads."""
    progress = pyqtSignal(int, str)
    log = pyqtSignal(str, str)
    finished = pyqtSignal(object)
    error = pyqtSignal(str)


class MainWindow(QMainWindow):
    """Main application window with connection tree and tabbed interface."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"OdooBench v{__version__}")
        self.setMinimumSize(1000, 700)

        # Initialize managers
        self.instance_manager = OdooInstanceManager()

        # Track open connections: {instance_id: {'executor': ..., 'tab': ..., 'feature_tabs': ...}}
        self.open_connections: Dict[int, Dict[str, Any]] = {}

        # Settings
        self.settings = QSettings('OdooBench', 'OdooBench')
        self._load_settings()

        # Build UI
        self._setup_menu()
        self._setup_central_widget()
        self._setup_statusbar()

        # Apply theme and font
        self._apply_theme()
        self._apply_font_size()

        # Restore window state
        self._restore_state()

        # Load connections
        self._refresh_connection_tree()

        # Restore open connections
        QTimer.singleShot(200, self._restore_open_connections)

    def _load_settings(self):
        """Load application settings."""
        self.dark_mode = self.settings.value('dark_mode', False, type=bool)
        self.font_size = self.settings.value('font_size', 10, type=int)
        self.backup_directory = self.settings.value(
            'backup_directory',
            os.path.expanduser('~/Documents/OdooBackups')
        )

    def _save_settings(self):
        """Save application settings."""
        self.settings.setValue('dark_mode', self.dark_mode)
        self.settings.setValue('font_size', self.font_size)
        self.settings.setValue('backup_directory', self.backup_directory)

    # =========================================================================
    # Menu Setup
    # =========================================================================

    def _setup_menu(self):
        """Setup the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        new_conn_action = QAction("&New Connection...", self)
        new_conn_action.setShortcut(QKeySequence("Ctrl+N"))
        new_conn_action.triggered.connect(self._new_connection)
        file_menu.addAction(new_conn_action)

        file_menu.addSeparator()

        export_action = QAction("&Export Connections...", self)
        export_action.triggered.connect(self._export_connections)
        file_menu.addAction(export_action)

        import_action = QAction("&Import Connections...", self)
        import_action.triggered.connect(self._import_connections)
        file_menu.addAction(import_action)

        file_menu.addSeparator()

        settings_action = QAction("&Settings...", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self._show_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")

        sync_action = QAction("&Order Sync...", self)
        sync_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        sync_action.triggered.connect(self._show_sync_dialog)
        tools_menu.addAction(sync_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_statusbar(self):
        """Setup the status bar."""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("Ready")

    # =========================================================================
    # Central Widget Setup
    # =========================================================================

    def _setup_central_widget(self):
        """Setup the main central widget with splitter."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(5, 5, 5, 5)

        # Splitter for left pane and main content
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.splitter)

        # Left pane - Connection tree
        self._setup_left_pane()

        # Right pane - Tab widget
        self._setup_right_pane()

        # Set splitter sizes
        self.splitter.setSizes([250, 750])

    def _setup_left_pane(self):
        """Setup the left pane with connection tree."""
        left_frame = QFrame()
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("Connections")
        header_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        add_btn = QPushButton("+")
        add_btn.setFixedWidth(30)
        add_btn.clicked.connect(self._new_connection)
        header_layout.addWidget(add_btn)

        left_layout.addLayout(header_layout)

        # Connection tree
        self.conn_tree = QTreeWidget()
        self.conn_tree.setHeaderHidden(True)
        self.conn_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.conn_tree.customContextMenuRequested.connect(self._show_connection_context_menu)
        self.conn_tree.itemDoubleClicked.connect(self._on_connection_double_click)
        left_layout.addWidget(self.conn_tree)

        self.splitter.addWidget(left_frame)

    def _setup_right_pane(self):
        """Setup the right pane with tab widget."""
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._on_tab_close)
        self.tab_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tab_widget.customContextMenuRequested.connect(self._show_tab_context_menu)

        # Welcome tab
        self._create_welcome_tab()

        self.splitter.addWidget(self.tab_widget)

    def _create_welcome_tab(self):
        """Create the welcome tab."""
        welcome = QWidget()
        layout = QVBoxLayout(welcome)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("OdooBench")
        title.setStyleSheet("font-size: 24pt; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Odoo Instance Manager")
        subtitle.setStyleSheet("font-size: 12pt;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        instructions = QLabel(
            "\nDouble-click a connection to open it,\n"
            "or create a new connection to get started."
        )
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(instructions)

        new_btn = QPushButton("New Connection")
        new_btn.clicked.connect(self._new_connection)
        layout.addWidget(new_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.tab_widget.addTab(welcome, "Welcome")

    # =========================================================================
    # Connection Tree
    # =========================================================================

    def _refresh_connection_tree(self):
        """Refresh the connection tree."""
        self.conn_tree.clear()

        groups = self.instance_manager.list_instances_by_group()

        for group_name, instances in sorted(groups.items()):
            group_item = QTreeWidgetItem([f"  {group_name}"])
            group_item.setData(0, Qt.ItemDataRole.UserRole, {'type': 'group', 'name': group_name})
            group_item.setExpanded(True)
            self.conn_tree.addTopLevelItem(group_item)

            for instance in instances:
                # Check if connected
                is_connected = instance['id'] in self.open_connections
                prefix = "● " if is_connected else "○ "
                name = prefix + instance['name']

                instance_item = QTreeWidgetItem([name])
                instance_item.setData(0, Qt.ItemDataRole.UserRole, {'type': 'instance', 'instance': instance})
                group_item.addChild(instance_item)

    def _show_connection_context_menu(self, pos):
        """Show context menu for connection tree."""
        item = self.conn_tree.itemAt(pos)
        if not item:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data.get('type') != 'instance':
            return

        menu = QMenu(self)

        connect_action = menu.addAction("Connect")
        connect_action.triggered.connect(lambda: self._connect_instance(data['instance']))

        edit_action = menu.addAction("Edit...")
        edit_action.triggered.connect(lambda: self._edit_instance(data['instance']))

        menu.addSeparator()

        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self._delete_instance(data['instance']))

        menu.exec(self.conn_tree.mapToGlobal(pos))

    def _on_connection_double_click(self, item, column):
        """Handle double-click on connection."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data.get('type') == 'instance':
            self._connect_instance(data['instance'])

    # =========================================================================
    # Tab Management
    # =========================================================================

    def _show_tab_context_menu(self, pos):
        """Show context menu for tabs."""
        tab_bar = self.tab_widget.tabBar()
        tab_index = tab_bar.tabAt(pos)
        if tab_index < 0 or tab_index == 0:  # Skip welcome tab
            return

        menu = QMenu(self)

        close_action = menu.addAction("Close Tab")
        close_action.triggered.connect(lambda: self._close_tab(tab_index))

        close_others_action = menu.addAction("Close Other Tabs")
        close_others_action.triggered.connect(lambda: self._close_other_tabs(tab_index))

        close_all_action = menu.addAction("Close All Tabs")
        close_all_action.triggered.connect(self._close_all_tabs)

        menu.exec(tab_bar.mapToGlobal(pos))

    def _on_tab_close(self, index):
        """Handle tab close request."""
        if index == 0:  # Don't close welcome tab
            return
        self._close_tab(index)

    def _close_tab(self, index):
        """Close a specific tab."""
        widget = self.tab_widget.widget(index)

        # Find which connection this tab belongs to
        for instance_id, conn_info in list(self.open_connections.items()):
            if conn_info.get('tab') == widget:
                del self.open_connections[instance_id]
                break

        self.tab_widget.removeTab(index)
        self._refresh_connection_tree()

    def _close_other_tabs(self, keep_index):
        """Close all tabs except the specified one."""
        # Close from end to start to maintain indices
        for i in range(self.tab_widget.count() - 1, 0, -1):
            if i != keep_index:
                self._close_tab(i)

    def _close_all_tabs(self):
        """Close all connection tabs."""
        for i in range(self.tab_widget.count() - 1, 0, -1):
            self._close_tab(i)

    # =========================================================================
    # Connection Management
    # =========================================================================

    def _new_connection(self):
        """Show dialog to create new connection."""
        dialog = ConnectionDialog(self, self.instance_manager)
        if dialog.exec() and dialog.result:
            self._refresh_connection_tree()

    def _edit_instance(self, instance):
        """Edit an existing connection."""
        # Fetch full instance data (list_instances only returns summary)
        full_instance = self.instance_manager.get_instance(instance['id'])
        if not full_instance:
            QMessageBox.warning(self, "Error", "Connection not found")
            return
        dialog = ConnectionDialog(self, self.instance_manager, full_instance)
        if dialog.exec() and dialog.result:
            self._refresh_connection_tree()

    def _delete_instance(self, instance):
        """Delete a connection."""
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete '{instance['name']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            # Close tab if open
            if instance['id'] in self.open_connections:
                conn_info = self.open_connections[instance['id']]
                index = self.tab_widget.indexOf(conn_info['tab'])
                if index >= 0:
                    self._close_tab(index)

            self.instance_manager.delete_instance(instance['id'])
            self._refresh_connection_tree()

    def _connect_instance(self, instance):
        """Open a connection tab for an instance."""
        instance_id = instance['id']

        # Already open?
        if instance_id in self.open_connections:
            # Switch to existing tab
            tab = self.open_connections[instance_id]['tab']
            self.tab_widget.setCurrentWidget(tab)
            return

        # Fetch full instance data (list_instances_by_group only returns summary)
        full_instance = self.instance_manager.get_instance(instance_id)
        if not full_instance:
            QMessageBox.warning(self, "Error", "Connection not found")
            return

        # Create executor
        exec_config = self.instance_manager.get_executor_config(instance_id)
        try:
            executor = create_executor(exec_config)
        except Exception as e:
            QMessageBox.critical(self, "Connection Error", f"Failed to connect:\n{e}")
            return

        # Create connection tab
        tab = self._create_connection_tab(full_instance, executor)

        # Store connection info
        self.open_connections[instance_id] = {
            'instance': full_instance,
            'executor': executor,
            'tab': tab,
        }

        # Add and switch to tab
        self.tab_widget.addTab(tab, full_instance['name'])
        self.tab_widget.setCurrentWidget(tab)

        # Refresh tree to show connected status
        self._refresh_connection_tree()

    def _create_connection_tab(self, instance, executor) -> QWidget:
        """Create the tabbed interface for a connection."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        # Feature tabs
        feature_tabs = QTabWidget()
        layout.addWidget(feature_tabs)

        instance_id = instance['id']

        # Logs tab
        logs_tab = self._create_logs_tab(instance, executor)
        feature_tabs.addTab(logs_tab, "Logs")

        # Database tab
        db_tab = self._create_database_tab(instance)
        feature_tabs.addTab(db_tab, "Database")

        # Backup tab
        backup_tab = self._create_backup_tab(instance)
        feature_tabs.addTab(backup_tab, "Backup")

        # Restore tab (if allowed)
        if instance.get('allow_restore'):
            restore_tab = self._create_restore_tab(instance)
            feature_tabs.addTab(restore_tab, "Restore")

        # Backup & Restore tab
        br_tab = self._create_backup_restore_tab(instance)
        feature_tabs.addTab(br_tab, "Backup & Restore")

        # History tab
        history_tab = self._create_history_tab(instance)
        feature_tabs.addTab(history_tab, "History")

        # Docker Export tab
        docker_tab = self._create_docker_export_tab(instance)
        feature_tabs.addTab(docker_tab, "Docker Export")

        return container

    # =========================================================================
    # Logs Tab
    # =========================================================================

    def _create_logs_tab(self, instance, executor) -> QWidget:
        """Create the logs tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Toolbar
        toolbar = QHBoxLayout()

        toolbar.addWidget(QLabel("Log Path:"))
        log_path_edit = QLineEdit()
        log_path_edit.setText(instance.get('log_path') or '')
        toolbar.addWidget(log_path_edit)

        toolbar.addWidget(QLabel("Lines:"))
        lines_combo = QComboBox()
        lines_combo.addItems(['100', '500', '1000', '5000', 'All'])
        lines_combo.setCurrentIndex(0)
        toolbar.addWidget(lines_combo)

        load_btn = QPushButton("Load")
        toolbar.addWidget(load_btn)

        follow_check = QCheckBox("Follow")
        toolbar.addWidget(follow_check)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Log viewer
        log_viewer = LogViewer()
        log_viewer.set_dark_mode(self.dark_mode)
        layout.addWidget(log_viewer)

        # Connect load button
        def load_logs():
            path = log_path_edit.text()
            lines = lines_combo.currentText()
            limit = None if lines == 'All' else int(lines)

            try:
                if instance.get('is_local'):
                    # Local file
                    with open(path, 'r') as f:
                        all_lines = f.readlines()
                        if limit:
                            all_lines = all_lines[-limit:]
                        log_viewer.set_lines([l.rstrip() for l in all_lines])
                else:
                    # Remote via SSH
                    cmd = f"tail -n {limit or 10000} '{path}'"
                    stdout, stderr, code = executor.run_command(cmd)
                    if code != 0:
                        raise Exception(stderr or f"Command failed with code {code}")
                    log_viewer.set_lines(stdout.split('\n'))

                self.statusbar.showMessage(f"Loaded {log_viewer._all_lines.__len__()} lines")

            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to load logs: {e}")

        load_btn.clicked.connect(load_logs)

        return tab

    # =========================================================================
    # Database Tab
    # =========================================================================

    def _create_database_tab(self, instance) -> QWidget:
        """Create the database tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Buttons
        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("Refresh All")
        test_btn = QPushButton("Test Connection")
        list_dbs_btn = QPushButton("List Databases")
        btn_layout.addWidget(refresh_btn)
        btn_layout.addWidget(test_btn)
        btn_layout.addWidget(list_dbs_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Info group
        info_group = QGroupBox("Database Information")
        info_layout = QFormLayout(info_group)

        version_label = QLabel("-")
        info_layout.addRow("PostgreSQL Version:", version_label)

        db_name_label = QLabel(instance.get('db_name', '-'))
        info_layout.addRow("Database:", db_name_label)

        host_label = QLabel(f"{instance.get('db_host', '-')}:{instance.get('db_port', 5432)}")
        info_layout.addRow("Host:", host_label)

        layout.addWidget(info_group)

        # Splitter for settings and results
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Settings table
        settings_group = QGroupBox("PostgreSQL Settings")
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setContentsMargins(5, 5, 5, 5)

        settings_table = QTableWidget()
        settings_table.setColumnCount(3)
        settings_table.setHorizontalHeaderLabels(['Setting', 'Value', 'Unit'])
        settings_table.horizontalHeader().setStretchLastSection(True)
        settings_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        settings_layout.addWidget(settings_table)

        splitter.addWidget(settings_group)

        # Results text
        results_group = QGroupBox("Query Results")
        results_layout = QVBoxLayout(results_group)
        results_layout.setContentsMargins(5, 5, 5, 5)
        results_text = QTextEdit()
        results_text.setReadOnly(True)
        results_layout.addWidget(results_text)

        splitter.addWidget(results_group)
        splitter.setSizes([300, 150])

        layout.addWidget(splitter)

        # Connect buttons
        def test_connection():
            bench = OdooBench(conn_manager=self.instance_manager)
            config = {
                'db_host': instance.get('db_host', 'localhost'),
                'db_port': instance.get('db_port', 5432),
                'db_user': instance.get('db_user', 'odoo'),
                'db_password': instance.get('db_password', ''),
                'db_name': instance.get('db_name', ''),
                'filestore_path': instance.get('filestore_path', ''),
                # SSH settings for remote connections
                'host': instance.get('host', 'localhost'),
                'ssh_port': instance.get('ssh_port', 22),
                'ssh_username': instance.get('ssh_username', ''),
                'ssh_password': instance.get('ssh_password', ''),
                'ssh_key_path': instance.get('ssh_key_path', ''),
            }
            # Add SSH flags for remote filestore testing
            if not instance.get('is_local') and instance.get('ssh_username'):
                config['use_ssh'] = True
                config['ssh_connection_id'] = instance['id']

            success, message = bench.test_connection(config)
            results_text.setText(message)
            if success:
                QMessageBox.information(self, "Connection Test", "Connection successful!")
            else:
                QMessageBox.warning(self, "Connection Test", message)

        def list_databases():
            bench = OdooBench(conn_manager=self.instance_manager)
            config = {
                'db_host': instance.get('db_host', 'localhost'),
                'db_port': instance.get('db_port', 5432),
                'db_user': instance.get('db_user', 'odoo'),
                'db_password': instance.get('db_password', ''),
            }
            try:
                databases = bench.list_databases(config)
                if databases:
                    results_text.setText("Databases:\n" + "\n".join(f"  • {db}" for db in databases))
                else:
                    results_text.setText("No databases found")
            except Exception as e:
                results_text.setText(f"Error listing databases: {e}")

        def refresh_all():
            bench = OdooBench(conn_manager=self.instance_manager)
            config = {
                'db_host': instance.get('db_host', 'localhost'),
                'db_port': instance.get('db_port', 5432),
                'db_user': instance.get('db_user', 'odoo'),
                'db_password': instance.get('db_password', ''),
                'db_name': instance.get('db_name', 'postgres'),
            }
            try:
                # Get PostgreSQL version
                version = bench.get_pg_version(config)
                version_label.setText(version or "-")

                # Get PostgreSQL settings
                settings = bench.get_pg_settings(config)
                settings_table.setRowCount(len(settings))
                for i, (name, value, unit) in enumerate(settings):
                    settings_table.setItem(i, 0, QTableWidgetItem(name))
                    settings_table.setItem(i, 1, QTableWidgetItem(value))
                    settings_table.setItem(i, 2, QTableWidgetItem(unit or ""))
                settings_table.resizeColumnsToContents()

                results_text.setText("Refresh complete")
            except Exception as e:
                results_text.setText(f"Error: {e}")

        test_btn.clicked.connect(test_connection)
        list_dbs_btn.clicked.connect(list_databases)
        refresh_btn.clicked.connect(refresh_all)

        return tab

    # =========================================================================
    # Backup Tab
    # =========================================================================

    def _create_backup_tab(self, instance) -> QWidget:
        """Create the backup tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Backup type
        type_group = QGroupBox("Backup Type")
        type_layout = QHBoxLayout(type_group)

        type_combo = QComboBox()
        type_combo.addItems(['Full Backup', 'Database Only', 'Filestore Only'])
        type_layout.addWidget(type_combo)
        type_layout.addStretch()

        layout.addWidget(type_group)

        # Destination
        dest_group = QGroupBox("Destination")
        dest_layout = QHBoxLayout(dest_group)

        dest_edit = QLineEdit()
        dest_edit.setText(self.backup_directory)
        dest_layout.addWidget(dest_edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(lambda: self._browse_directory(dest_edit))
        dest_layout.addWidget(browse_btn)

        layout.addWidget(dest_group)

        # Start button
        start_btn = QPushButton("Start Backup")
        start_btn.setStyleSheet("font-weight: bold; padding: 10px;")
        layout.addWidget(start_btn)

        # Progress
        progress = ProgressWidget(show_cancel=True)
        progress.set_dark_mode(self.dark_mode)
        layout.addWidget(progress)

        # Connect start button
        def start_backup():
            backup_type = type_combo.currentText()
            backup_dir = dest_edit.text()

            config = {
                'db_name': instance.get('db_name'),
                'db_host': instance.get('db_host', 'localhost'),
                'db_port': instance.get('db_port', 5432),
                'db_user': instance.get('db_user', 'odoo'),
                'db_password': instance.get('db_password', ''),
                'filestore_path': instance.get('filestore_path', ''),
                'backup_dir': backup_dir,
                'db_only': backup_type == 'Database Only',
                'filestore_only': backup_type == 'Filestore Only',
            }

            # Add SSH config if needed
            if not instance.get('is_local') and instance.get('ssh_username'):
                config['use_ssh'] = True
                config['ssh_connection_id'] = instance['id']

            start_btn.setEnabled(False)
            progress.clear()

            def run_backup():
                try:
                    bench = OdooBench(
                        progress_callback=lambda v, m: progress.set_progress(v, m),
                        log_callback=lambda m, l: progress.add_log(m, l),
                        conn_manager=self.instance_manager
                    )
                    result = bench.backup(config)
                    self._on_backup_complete(instance, result, progress, start_btn)
                except Exception as e:
                    self._on_backup_error(str(e), progress, start_btn)

            threading.Thread(target=run_backup, daemon=True).start()

        start_btn.clicked.connect(start_backup)

        return tab

    def _on_backup_complete(self, instance, result, progress, start_btn):
        """Handle backup completion."""
        def update():
            progress.set_complete(True)
            progress.add_log(f"Backup saved to: {result}", "success")
            start_btn.setEnabled(True)
            QMessageBox.information(self, "Backup Complete", f"Backup saved to:\n{result}")

        QTimer.singleShot(0, update)

    def _on_backup_error(self, error, progress, start_btn):
        """Handle backup error."""
        def update():
            progress.add_log(f"Error: {error}", "error")
            start_btn.setEnabled(True)
            QMessageBox.critical(self, "Backup Failed", error)

        QTimer.singleShot(0, update)

    # =========================================================================
    # Restore Tab
    # =========================================================================

    def _create_restore_tab(self, instance) -> QWidget:
        """Create the restore tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # File selection
        file_group = QGroupBox("Backup File")
        file_layout = QHBoxLayout(file_group)

        file_edit = QLineEdit()
        file_edit.setPlaceholderText("Select backup file...")
        file_layout.addWidget(file_edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(lambda: self._browse_backup_file(file_edit))
        file_layout.addWidget(browse_btn)

        layout.addWidget(file_group)

        # Recent backups
        recent_group = QGroupBox("Recent Backups")
        recent_layout = QVBoxLayout(recent_group)

        recent_list = QListWidget()
        recent_list.setMaximumHeight(150)
        recent_layout.addWidget(recent_list)

        refresh_btn = QPushButton("Refresh")
        recent_layout.addWidget(refresh_btn)

        layout.addWidget(recent_group)

        # Options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        type_combo = QComboBox()
        type_combo.addItems(['Full Restore', 'Database Only', 'Filestore Only'])
        options_layout.addWidget(type_combo)

        neutralize_check = QCheckBox("Neutralize database after restore")
        neutralize_check.setChecked(True)
        options_layout.addWidget(neutralize_check)

        layout.addWidget(options_group)

        # Start button
        start_btn = QPushButton("Start Restore")
        start_btn.setStyleSheet("font-weight: bold; padding: 10px;")
        layout.addWidget(start_btn)

        # Progress
        progress = ProgressWidget(show_cancel=True)
        progress.set_dark_mode(self.dark_mode)
        layout.addWidget(progress)

        # Load recent backups
        def refresh_recent():
            recent_list.clear()
            if os.path.exists(self.backup_directory):
                files = sorted(
                    [f for f in os.listdir(self.backup_directory) if f.endswith('.tar.gz')],
                    reverse=True
                )[:10]
                for f in files:
                    recent_list.addItem(f)

        refresh_btn.clicked.connect(refresh_recent)
        recent_list.itemDoubleClicked.connect(
            lambda item: file_edit.setText(os.path.join(self.backup_directory, item.text()))
        )

        # Connect start button
        def start_restore():
            backup_file = file_edit.text()
            if not backup_file or not os.path.exists(backup_file):
                QMessageBox.warning(self, "Error", "Please select a valid backup file")
                return

            restore_type = type_combo.currentText()
            neutralize = neutralize_check.isChecked()

            config = {
                'db_name': instance.get('db_name'),
                'db_host': instance.get('db_host', 'localhost'),
                'db_port': instance.get('db_port', 5432),
                'db_user': instance.get('db_user', 'odoo'),
                'db_password': instance.get('db_password', ''),
                'filestore_path': instance.get('filestore_path', ''),
                'neutralize': neutralize,
                'db_only': restore_type == 'Database Only',
                'filestore_only': restore_type == 'Filestore Only',
            }

            if not instance.get('is_local') and instance.get('ssh_username'):
                config['use_ssh'] = True
                config['ssh_connection_id'] = instance['id']

            start_btn.setEnabled(False)
            progress.clear()

            def run_restore():
                try:
                    bench = OdooBench(
                        progress_callback=lambda v, m: progress.set_progress(v, m),
                        log_callback=lambda m, l: progress.add_log(m, l),
                        conn_manager=self.instance_manager
                    )
                    bench.restore(config, backup_file)
                    self._on_restore_complete(progress, start_btn)
                except Exception as e:
                    self._on_restore_error(str(e), progress, start_btn)

            threading.Thread(target=run_restore, daemon=True).start()

        start_btn.clicked.connect(start_restore)

        # Initial load
        refresh_recent()

        return tab

    def _on_restore_complete(self, progress, start_btn):
        """Handle restore completion."""
        def update():
            progress.set_complete(True)
            progress.add_log("Restore completed successfully!", "success")
            start_btn.setEnabled(True)
            QMessageBox.information(self, "Restore Complete", "Database restored successfully!")

        QTimer.singleShot(0, update)

    def _on_restore_error(self, error, progress, start_btn):
        """Handle restore error."""
        def update():
            progress.add_log(f"Error: {error}", "error")
            start_btn.setEnabled(True)
            QMessageBox.critical(self, "Restore Failed", error)

        QTimer.singleShot(0, update)

    # =========================================================================
    # Backup & Restore Tab
    # =========================================================================

    def _create_backup_restore_tab(self, instance) -> QWidget:
        """Create the backup & restore tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Destination selection
        dest_group = QGroupBox("Destination Connection")
        dest_layout = QFormLayout(dest_group)

        dest_combo = QComboBox()
        dest_layout.addRow("Restore to:", dest_combo)

        dest_info = QLabel("-")
        dest_layout.addRow("Info:", dest_info)

        layout.addWidget(dest_group)

        # Options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        type_combo = QComboBox()
        type_combo.addItems(['Full Backup & Restore', 'Database Only', 'Filestore Only'])
        options_layout.addWidget(type_combo)

        neutralize_check = QCheckBox("Neutralize destination after restore")
        neutralize_check.setChecked(True)
        options_layout.addWidget(neutralize_check)

        layout.addWidget(options_group)

        # Start button
        start_btn = QPushButton("Start Backup & Restore")
        start_btn.setStyleSheet("font-weight: bold; padding: 10px;")
        layout.addWidget(start_btn)

        # Progress
        progress = ProgressWidget(show_cancel=True)
        progress.set_dark_mode(self.dark_mode)
        layout.addWidget(progress)

        # Refresh destinations
        def refresh_destinations():
            dest_combo.clear()
            instances = self.instance_manager.list_instances()
            for inst in instances:
                if inst.get('allow_restore') and inst['id'] != instance['id']:
                    dest_combo.addItem(inst['name'], inst['id'])

        def update_dest_info():
            idx = dest_combo.currentIndex()
            if idx >= 0:
                dest_id = dest_combo.currentData()
                dest = self.instance_manager.get_instance(dest_id)
                if dest:
                    dest_info.setText(f"{dest.get('db_name', '')} @ {dest.get('db_host', '')}")

        dest_combo.currentIndexChanged.connect(update_dest_info)

        # Connect start button
        def start_backup_restore():
            if dest_combo.currentIndex() < 0:
                QMessageBox.warning(self, "Error", "Please select a destination")
                return

            dest_id = dest_combo.currentData()
            dest = self.instance_manager.get_instance(dest_id)

            br_type = type_combo.currentText()
            neutralize = neutralize_check.isChecked()

            source_config = {
                'db_name': instance.get('db_name'),
                'db_host': instance.get('db_host', 'localhost'),
                'db_port': instance.get('db_port', 5432),
                'db_user': instance.get('db_user', 'odoo'),
                'db_password': instance.get('db_password', ''),
                'filestore_path': instance.get('filestore_path', ''),
                'backup_dir': self.backup_directory,
                'db_only': 'Database' in br_type,
                'filestore_only': 'Filestore' in br_type,
            }

            dest_config = {
                'db_name': dest.get('db_name'),
                'db_host': dest.get('db_host', 'localhost'),
                'db_port': dest.get('db_port', 5432),
                'db_user': dest.get('db_user', 'odoo'),
                'db_password': dest.get('db_password', ''),
                'filestore_path': dest.get('filestore_path', ''),
                'neutralize': neutralize,
                'db_only': 'Database' in br_type,
                'filestore_only': 'Filestore' in br_type,
            }

            # Add SSH config if needed
            if not instance.get('is_local') and instance.get('ssh_username'):
                source_config['use_ssh'] = True
                source_config['ssh_connection_id'] = instance['id']

            if not dest.get('is_local') and dest.get('ssh_username'):
                dest_config['use_ssh'] = True
                dest_config['ssh_connection_id'] = dest['id']

            start_btn.setEnabled(False)
            progress.clear()

            def run_br():
                try:
                    bench = OdooBench(
                        progress_callback=lambda v, m: progress.set_progress(v, m),
                        log_callback=lambda m, l: progress.add_log(m, l),
                        conn_manager=self.instance_manager
                    )
                    bench.backup_and_restore(source_config, dest_config)
                    self._on_restore_complete(progress, start_btn)
                except Exception as e:
                    self._on_restore_error(str(e), progress, start_btn)

            threading.Thread(target=run_br, daemon=True).start()

        start_btn.clicked.connect(start_backup_restore)

        # Initial load
        refresh_destinations()
        update_dest_info()

        return tab

    # =========================================================================
    # History Tab
    # =========================================================================

    def _create_history_tab(self, instance) -> QWidget:
        """Create the history tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("Operation History"))
        header.addStretch()
        refresh_btn = QPushButton("Refresh")
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        # Operations table
        ops_table = QTableWidget()
        ops_table.setColumnCount(4)
        ops_table.setHorizontalHeaderLabels(['Date', 'Operation', 'Status', 'Backup File'])
        ops_table.horizontalHeader().setStretchLastSection(True)
        ops_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        ops_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(ops_table)

        # Log detail
        log_group = QGroupBox("Operation Log")
        log_layout = QVBoxLayout(log_group)
        log_text = QTextEdit()
        log_text.setReadOnly(True)
        log_text.setFont(QFont("monospace", 9))
        log_layout.addWidget(log_text)
        layout.addWidget(log_group)

        # Store logs data
        logs_data = {}

        def refresh_history():
            ops_table.setRowCount(0)
            logs_data.clear()

            logs = self.instance_manager.get_operation_logs(instance_id=instance['id'], limit=50)
            ops_table.setRowCount(len(logs))

            for row, log in enumerate(logs):
                logs_data[row] = log

                completed = log.get('completed_at', '')
                if completed:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(completed.replace('Z', '+00:00'))
                        date_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        date_str = completed
                else:
                    date_str = 'Unknown'

                ops_table.setItem(row, 0, QTableWidgetItem(date_str))
                ops_table.setItem(row, 1, QTableWidgetItem(log.get('operation_type', '').replace('_', ' ').title()))

                status = log.get('status', '')
                status_item = QTableWidgetItem('✓ ' + status.title() if status == 'success' else '✗ ' + status.title())
                ops_table.setItem(row, 2, status_item)

                backup_file = log.get('backup_file', '')
                if backup_file:
                    backup_file = os.path.basename(backup_file)
                ops_table.setItem(row, 3, QTableWidgetItem(backup_file))

        def on_select(selected, deselected):
            indexes = ops_table.selectionModel().selectedRows()
            if indexes:
                row = indexes[0].row()
                log = logs_data.get(row)
                if log:
                    log_text.setText(log.get('log_text', 'No log content available'))

        refresh_btn.clicked.connect(refresh_history)
        ops_table.selectionModel().selectionChanged.connect(on_select)

        # Initial load
        refresh_history()

        return tab

    # =========================================================================
    # Docker Export Tab
    # =========================================================================

    def _create_docker_export_tab(self, instance) -> QWidget:
        """Create the Docker Export tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("Docker Export"))
        header.addWidget(QLabel(" - Create a self-contained Docker package"))
        header.addStretch()
        layout.addLayout(header)

        # Profile selection
        profile_group = QGroupBox("Export Profile")
        profile_layout = QHBoxLayout(profile_group)

        profile_combo = QComboBox()
        profile_combo.setMinimumWidth(300)
        profile_layout.addWidget(profile_combo)

        new_btn = QPushButton("New")
        edit_btn = QPushButton("Edit")
        delete_btn = QPushButton("Delete")
        profile_layout.addWidget(new_btn)
        profile_layout.addWidget(edit_btn)
        profile_layout.addWidget(delete_btn)
        profile_layout.addStretch()

        layout.addWidget(profile_group)

        # Profile summary
        summary_group = QGroupBox("Profile Summary")
        summary_layout = QFormLayout(summary_group)

        source_dir_label = QLabel("-")
        summary_layout.addRow("Source Directory:", source_dir_label)

        subdirs_label = QLabel("-")
        summary_layout.addRow("Subdirectories:", subdirs_label)

        python_label = QLabel("-")
        summary_layout.addRow("Python Version:", python_label)

        pg_label = QLabel("-")
        summary_layout.addRow("PostgreSQL:", pg_label)

        port_label = QLabel("-")
        summary_layout.addRow("Odoo Port:", port_label)

        layout.addWidget(summary_group)

        # Export button
        export_btn = QPushButton("Start Docker Export")
        export_btn.setStyleSheet("font-weight: bold; padding: 10px;")
        layout.addWidget(export_btn)

        # Progress
        progress = ProgressWidget(show_cancel=True)
        progress.set_dark_mode(self.dark_mode)
        layout.addWidget(progress)

        # Functions
        def refresh_profiles():
            profile_combo.clear()
            profiles = self.instance_manager.list_docker_export_profiles(odoo_instance_id=instance['id'])
            for p in profiles:
                profile_combo.addItem(p['name'], p['id'])

        def update_summary():
            idx = profile_combo.currentIndex()
            if idx < 0:
                source_dir_label.setText("-")
                subdirs_label.setText("-")
                python_label.setText("-")
                pg_label.setText("-")
                port_label.setText("-")
                return

            profile = self.instance_manager.get_docker_export_profile(profile_combo.currentData())
            if profile:
                source_dir_label.setText(profile.get('source_base_dir', '-'))
                subdirs = profile.get('source_subdirs', '[]')
                try:
                    subdirs_list = json.loads(subdirs) if isinstance(subdirs, str) else subdirs
                    subdirs_label.setText(', '.join(subdirs_list[:3]) + ('...' if len(subdirs_list) > 3 else ''))
                except:
                    subdirs_label.setText('-')
                python_label.setText(profile.get('python_version', '3.12'))
                pg_label.setText(profile.get('postgres_version', '16'))
                port_label.setText(str(profile.get('odoo_port', 8069)))

        def new_profile():
            dialog = DockerExportProfileDialog(self, self.instance_manager, instance)
            if dialog.exec() and dialog.result:
                refresh_profiles()
                # Select the new profile
                idx = profile_combo.findText(dialog.result)
                if idx >= 0:
                    profile_combo.setCurrentIndex(idx)

        def edit_profile():
            if profile_combo.currentIndex() < 0:
                QMessageBox.warning(self, "No Profile", "Please select a profile to edit")
                return
            profile = self.instance_manager.get_docker_export_profile(profile_combo.currentData())
            if profile:
                dialog = DockerExportProfileDialog(self, self.instance_manager, instance, profile)
                if dialog.exec() and dialog.result:
                    refresh_profiles()
                    idx = profile_combo.findText(dialog.result)
                    if idx >= 0:
                        profile_combo.setCurrentIndex(idx)

        def delete_profile():
            if profile_combo.currentIndex() < 0:
                QMessageBox.warning(self, "No Profile", "Please select a profile to delete")
                return
            name = profile_combo.currentText()
            reply = QMessageBox.question(
                self, "Confirm Delete",
                f"Are you sure you want to delete profile '{name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.instance_manager.delete_docker_export_profile(profile_combo.currentData())
                refresh_profiles()

        def start_export():
            if profile_combo.currentIndex() < 0:
                QMessageBox.warning(self, "No Profile", "Please select or create a Docker export profile first")
                return

            profile = self.instance_manager.get_docker_export_profile(profile_combo.currentData())
            if not profile:
                QMessageBox.warning(self, "Error", "Profile not found")
                return

            source_config = {
                'db_name': instance.get('db_name'),
                'db_host': instance.get('db_host', 'localhost'),
                'db_port': instance.get('db_port', 5432),
                'db_user': instance.get('db_user', 'odoo'),
                'db_password': instance.get('db_password', ''),
                'filestore_path': instance.get('filestore_path', ''),
                'is_local': instance.get('is_local', False),
                'host': instance.get('host'),
                'ssh_port': instance.get('ssh_port', 22),
                'ssh_username': instance.get('ssh_username'),
                'ssh_password': instance.get('ssh_password'),
                'ssh_key_path': instance.get('ssh_key_path'),
                # PG server SSH (for running pg_dump directly on PG server)
                'pg_ssh_host': instance.get('pg_ssh_host'),
                'pg_ssh_port': instance.get('pg_ssh_port'),
                'pg_ssh_username': instance.get('pg_ssh_username'),
                'pg_ssh_password': instance.get('pg_ssh_password'),
                'pg_ssh_key_path': instance.get('pg_ssh_key_path'),
            }

            if not source_config['is_local'] and source_config.get('ssh_username'):
                source_config['use_ssh'] = True
                source_config['ssh_connection_id'] = instance['id']

            if not profile.get('output_dir'):
                profile['output_dir'] = self.backup_directory

            export_btn.setEnabled(False)
            progress.clear()

            def run_export():
                try:
                    from ..docker.exporter import DockerExporter
                    exporter = DockerExporter(
                        progress_callback=lambda v, m: progress.set_progress(v, m),
                        log_callback=lambda m, l: progress.add_log(m, l),
                        conn_manager=self.instance_manager
                    )
                    result = exporter.export(source_config, profile)

                    def on_complete():
                        progress.set_complete(True)
                        progress.add_log(f"Export saved to: {result}", "success")
                        export_btn.setEnabled(True)
                        QMessageBox.information(self, "Export Complete", f"Docker export saved to:\n{result}")

                    QTimer.singleShot(0, on_complete)

                except Exception as e:
                    def on_error():
                        progress.add_log(f"Error: {e}", "error")
                        export_btn.setEnabled(True)
                        QMessageBox.critical(self, "Export Failed", str(e))

                    QTimer.singleShot(0, on_error)

            threading.Thread(target=run_export, daemon=True).start()

        # Connect signals
        new_btn.clicked.connect(new_profile)
        edit_btn.clicked.connect(edit_profile)
        delete_btn.clicked.connect(delete_profile)
        export_btn.clicked.connect(start_export)
        profile_combo.currentIndexChanged.connect(update_summary)

        # Initial load
        refresh_profiles()
        update_summary()

        return tab

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _browse_directory(self, line_edit):
        """Browse for a directory."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Directory",
            line_edit.text() or os.path.expanduser("~")
        )
        if directory:
            line_edit.setText(directory)

    def _browse_backup_file(self, line_edit):
        """Browse for a backup file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select Backup File",
            self.backup_directory,
            "Backup Files (*.tar.gz);;All Files (*)"
        )
        if filepath:
            line_edit.setText(filepath)

    # =========================================================================
    # Settings & Theme
    # =========================================================================

    def _show_settings(self):
        """Show settings dialog."""
        settings = {
            'backup_directory': self.backup_directory,
            'font_size': self.font_size,
            'dark_mode': self.dark_mode,
        }
        dialog = SettingsDialog(self, settings)
        if dialog.exec():
            new_settings = dialog.get_settings()
            self.backup_directory = new_settings['backup_directory']
            self.font_size = new_settings['font_size']
            self.dark_mode = new_settings['dark_mode']
            self._save_settings()
            self._apply_theme()
            self._apply_font_size()

    def _apply_font_size(self):
        """Apply font size to the application."""
        font = QApplication.font()
        font.setPointSize(self.font_size)
        QApplication.setFont(font)
        # Force update on all widgets
        for widget in QApplication.allWidgets():
            widget.setFont(font)

    def _apply_theme(self):
        """Apply dark or light theme."""
        if self.dark_mode:
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background-color: #2b2b2b;
                    color: #a9b7c6;
                }
                QTreeWidget, QTableWidget, QListWidget, QTextEdit, QLineEdit, QComboBox, QSpinBox {
                    background-color: #313335;
                    color: #a9b7c6;
                    border: 1px solid #3c3f41;
                }
                QGroupBox {
                    border: 1px solid #3c3f41;
                    margin-top: 10px;
                    padding-top: 10px;
                }
                QGroupBox::title {
                    color: #a9b7c6;
                }
                QPushButton {
                    background-color: #3c3f41;
                    color: #a9b7c6;
                    border: 1px solid #555;
                    padding: 5px 15px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #4c5052;
                }
                QPushButton:pressed {
                    background-color: #2d2d2d;
                }
                QTabWidget::pane {
                    border: 1px solid #3c3f41;
                }
                QTabBar::tab {
                    background-color: #3c3f41;
                    color: #a9b7c6;
                    padding: 8px 16px;
                    border: 1px solid #3c3f41;
                }
                QTabBar::tab:selected {
                    background-color: #2b2b2b;
                }
                QMenuBar {
                    background-color: #3c3f41;
                    color: #a9b7c6;
                }
                QMenuBar::item:selected {
                    background-color: #4c5052;
                }
                QMenu {
                    background-color: #3c3f41;
                    color: #a9b7c6;
                }
                QMenu::item:selected {
                    background-color: #4c5052;
                }
                QProgressBar {
                    border: 1px solid #3c3f41;
                    background-color: #313335;
                }
                QProgressBar::chunk {
                    background-color: #629755;
                }
                QCheckBox {
                    color: #a9b7c6;
                }
                QLabel {
                    color: #a9b7c6;
                }
                QHeaderView::section {
                    background-color: #3c3f41;
                    color: #a9b7c6;
                    border: 1px solid #2b2b2b;
                }
            """)
        else:
            self.setStyleSheet("")

    def _show_about(self):
        """Show about dialog."""
        dialog = AboutDialog(self)
        dialog.exec()

    def _show_sync_dialog(self):
        """Show the order sync dialog."""
        dialog = SyncDialog(self, self.instance_manager, self.dark_mode)
        dialog.exec()

    # =========================================================================
    # Import/Export
    # =========================================================================

    def _export_connections(self):
        """Export connections to JSON file."""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Connections",
            os.path.expanduser("~/odoobench_connections.json"),
            "JSON Files (*.json)"
        )
        if filepath:
            try:
                data = self.instance_manager.export_connections()
                with open(filepath, 'w') as f:
                    json.dump(data, f, indent=2)
                QMessageBox.information(self, "Export Complete", f"Connections exported to:\n{filepath}")
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", str(e))

    def _import_connections(self):
        """Import connections from JSON file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import Connections",
            os.path.expanduser("~"),
            "JSON Files (*.json)"
        )
        if filepath:
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                success, errors, messages = self.instance_manager.import_connections(data)
                self._refresh_connection_tree()
                QMessageBox.information(
                    self, "Import Complete",
                    f"Imported: {success}\nErrors: {errors}\n\n" + '\n'.join(messages[:10])
                )
            except Exception as e:
                QMessageBox.critical(self, "Import Failed", str(e))

    # =========================================================================
    # State Persistence
    # =========================================================================

    def _restore_state(self):
        """Restore window state from settings."""
        geometry = self.settings.value('geometry')
        if geometry:
            self.restoreGeometry(geometry)

        state = self.settings.value('windowState')
        if state:
            self.restoreState(state)

        splitter_state = self.settings.value('splitterState')
        if splitter_state:
            self.splitter.restoreState(splitter_state)

    def _save_state(self):
        """Save window state to settings."""
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('windowState', self.saveState())
        self.settings.setValue('splitterState', self.splitter.saveState())

        # Save open connections
        open_ids = list(self.open_connections.keys())
        self.settings.setValue('openConnections', open_ids)

    def _restore_open_connections(self):
        """Restore previously open connections."""
        open_ids = self.settings.value('openConnections', [])
        if not open_ids:
            return

        for instance_id in open_ids:
            try:
                instance = self.instance_manager.get_instance(instance_id)
                if instance:
                    self._connect_instance(instance)
            except Exception as e:
                print(f"Failed to restore connection {instance_id}: {e}")

    def closeEvent(self, event: QCloseEvent):
        """Handle window close."""
        self._save_state()
        self._save_settings()
        event.accept()


def launch():
    """Launch the Qt GUI."""
    import sys
    app = QApplication(sys.argv)
    app.setApplicationName("OdooBench")
    app.setOrganizationName("OdooBench")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
