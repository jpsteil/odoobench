"""Sync Dialog for Odoo Order Sync."""

import threading
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QPushButton, QComboBox, QCheckBox, QLabel, QMessageBox, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

from ..widgets.progress_widget import ProgressWidget


class SyncSignals(QObject):
    """Signals for sync thread communication."""
    progress = pyqtSignal(int, str)
    log = pyqtSignal(str, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)


class SyncDialog(QDialog):
    """Dialog for configuring and running order sync."""

    def __init__(self, parent=None, instance_manager=None, dark_mode=False):
        super().__init__(parent)
        self.instance_manager = instance_manager
        self.dark_mode = dark_mode
        self.sync_engine = None
        self.sync_thread = None
        self._is_syncing = False

        self.setWindowTitle("Order Sync")
        self.setMinimumSize(700, 600)
        self.setModal(False)  # Allow interaction with main window

        self._setup_ui()
        self._refresh_connections()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Warning banner
        warning = QLabel(
            "WARNING: This tool syncs records from a source Odoo to a target Odoo. "
            "Only connections with 'Allow Sync' enabled can be targets."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "background-color: #ff6b6b; color: white; padding: 10px; "
            "border-radius: 5px; font-weight: bold;"
        )
        layout.addWidget(warning)

        # Connection selection
        conn_group = QGroupBox("Connections")
        conn_layout = QFormLayout(conn_group)

        # Source connection
        source_layout = QHBoxLayout()
        self.source_combo = QComboBox()
        self.source_combo.setMinimumWidth(300)
        source_layout.addWidget(self.source_combo)
        self.source_test_btn = QPushButton("Test")
        self.source_test_btn.clicked.connect(lambda: self._test_connection('source'))
        source_layout.addWidget(self.source_test_btn)
        conn_layout.addRow("Source (Production):", source_layout)

        # Target connection
        target_layout = QHBoxLayout()
        self.target_combo = QComboBox()
        self.target_combo.setMinimumWidth(300)
        target_layout.addWidget(self.target_combo)
        self.target_test_btn = QPushButton("Test")
        self.target_test_btn.clicked.connect(lambda: self._test_connection('target'))
        target_layout.addWidget(self.target_test_btn)
        conn_layout.addRow("Target (Replica):", target_layout)

        # Connection status
        self.conn_status = QLabel("")
        conn_layout.addRow("", self.conn_status)

        layout.addWidget(conn_group)

        # Sync options
        options_group = QGroupBox("Sync Options")
        options_layout = QFormLayout(options_group)

        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(10, 1000)
        self.batch_size_spin.setValue(100)
        self.batch_size_spin.setSuffix(" records")
        options_layout.addRow("Batch Size:", self.batch_size_spin)

        self.include_deletes_check = QCheckBox("Detect and remove deleted records")
        self.include_deletes_check.setChecked(True)
        options_layout.addRow("", self.include_deletes_check)

        layout.addWidget(options_group)

        # Sync stats
        stats_group = QGroupBox("Sync Statistics")
        stats_layout = QFormLayout(stats_group)

        self.so_count_label = QLabel("0")
        stats_layout.addRow("Sale Orders Synced:", self.so_count_label)

        self.sol_count_label = QLabel("0")
        stats_layout.addRow("Sale Order Lines Synced:", self.sol_count_label)

        self.last_sync_label = QLabel("Never")
        stats_layout.addRow("Last Sync:", self.last_sync_label)

        layout.addWidget(stats_group)

        # Control buttons
        button_layout = QHBoxLayout()

        self.start_btn = QPushButton("Start Sync")
        self.start_btn.setStyleSheet(
            "font-weight: bold; padding: 10px; "
            "background-color: #4CAF50; color: white;"
        )
        self.start_btn.clicked.connect(self._start_sync)
        button_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("padding: 10px;")
        self.stop_btn.clicked.connect(self._stop_sync)
        button_layout.addWidget(self.stop_btn)

        button_layout.addStretch()

        self.refresh_btn = QPushButton("Refresh Stats")
        self.refresh_btn.clicked.connect(self._refresh_stats)
        button_layout.addWidget(self.refresh_btn)

        layout.addLayout(button_layout)

        # Progress widget
        self.progress = ProgressWidget(show_cancel=False)
        self.progress.set_dark_mode(self.dark_mode)
        layout.addWidget(self.progress)

        # Close button
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        close_layout.addWidget(close_btn)
        layout.addLayout(close_layout)

    def _refresh_connections(self):
        """Refresh the connection dropdowns."""
        self.source_combo.clear()
        self.target_combo.clear()

        instances = self.instance_manager.list_instances()

        for inst in instances:
            # All connections can be sources
            self.source_combo.addItem(
                f"{inst['name']} ({inst.get('db_name', 'N/A')})",
                inst['id']
            )

            # Only allow_sync connections can be targets
            if inst.get('allow_sync'):
                self.target_combo.addItem(
                    f"{inst['name']} ({inst.get('db_name', 'N/A')})",
                    inst['id']
                )

        if self.target_combo.count() == 0:
            self.target_combo.addItem("No sync-enabled connections", None)
            self.start_btn.setEnabled(False)
            self.conn_status.setText(
                "No connections have 'Allow Sync' enabled. "
                "Edit a connection to enable it."
            )
            self.conn_status.setStyleSheet("color: red;")
        else:
            self.start_btn.setEnabled(True)
            self.conn_status.setText("")

        self._refresh_stats()

    def _test_connection(self, which: str):
        """Test a connection via OdooRPC."""
        try:
            import odoorpc
        except ImportError:
            QMessageBox.critical(
                self, "Missing Dependency",
                "odoorpc is required for sync.\nInstall with: pip install odoorpc"
            )
            return

        combo = self.source_combo if which == 'source' else self.target_combo
        instance_id = combo.currentData()

        if not instance_id:
            QMessageBox.warning(self, "No Connection", "Please select a connection first")
            return

        instance = self.instance_manager.get_instance(instance_id)
        if not instance:
            QMessageBox.warning(self, "Error", "Connection not found")
            return

        try:
            # Derive host from connection settings
            if instance.get('host') and instance.get('host') != 'localhost':
                host = instance.get('host')
            else:
                host = 'localhost'

            port = instance.get('odoo_http_port', 8069)

            odoo = odoorpc.ODOO(host, port=port)
            odoo.login(
                instance.get('db_name'),
                instance.get('odoo_user') or 'admin',
                instance.get('odoo_password') or ''
            )

            QMessageBox.information(
                self, "Connection Test",
                f"Successfully connected to {instance['name']}!\n"
                f"Odoo version: {odoo.version}"
            )

        except Exception as e:
            QMessageBox.warning(
                self, "Connection Test Failed",
                f"Failed to connect to {instance['name']}:\n{e}"
            )

    def _refresh_stats(self):
        """Refresh sync statistics."""
        source_id = self.source_combo.currentData()
        target_id = self.target_combo.currentData()

        if not source_id or not target_id:
            return

        stats = self.instance_manager.get_sync_stats(source_id, target_id)

        self.so_count_label.setText(str(stats.get('sale.order', 0)))
        self.sol_count_label.setText(str(stats.get('sale.order.line', 0)))

        last_sync = self.instance_manager.get_last_sync_time(
            'sale.order', source_id, target_id
        )
        self.last_sync_label.setText(last_sync or "Never")

    def _start_sync(self):
        """Start the sync process."""
        try:
            from ...sync import SyncEngine
        except ImportError as e:
            QMessageBox.critical(
                self, "Import Error",
                f"Failed to import sync module: {e}\n\n"
                "Make sure odoorpc is installed: pip install odoorpc"
            )
            return

        source_id = self.source_combo.currentData()
        target_id = self.target_combo.currentData()

        if not source_id or not target_id:
            QMessageBox.warning(self, "Error", "Please select both source and target connections")
            return

        if source_id == target_id:
            QMessageBox.warning(self, "Error", "Source and target cannot be the same connection")
            return

        # Confirm sync
        source_name = self.source_combo.currentText()
        target_name = self.target_combo.currentText()

        reply = QMessageBox.question(
            self, "Confirm Sync",
            f"This will sync records FROM:\n  {source_name}\n\n"
            f"TO:\n  {target_name}\n\n"
            "This operation will create, update, and potentially delete records "
            "on the target database.\n\n"
            "Are you sure you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Setup UI for syncing
        self._is_syncing = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.source_combo.setEnabled(False)
        self.target_combo.setEnabled(False)
        self.progress.clear()

        # Create signals for thread communication
        self.signals = SyncSignals()
        self.signals.progress.connect(self.progress.set_progress)
        self.signals.log.connect(self.progress.add_log)
        self.signals.finished.connect(self._on_sync_finished)
        self.signals.error.connect(self._on_sync_error)

        # Create sync engine
        self.sync_engine = SyncEngine(
            instance_manager=self.instance_manager,
            progress_callback=lambda p, m: self.signals.progress.emit(p, m),
            log_callback=lambda m, l: self.signals.log.emit(m, l),
        )

        # Run sync in thread
        def run_sync():
            try:
                # Connect
                if not self.sync_engine.connect(source_id, target_id):
                    self.signals.error.emit("Failed to connect to one or both instances")
                    return

                # Run sync
                results = self.sync_engine.run_full_sync(
                    include_deletes=self.include_deletes_check.isChecked(),
                    batch_size=self.batch_size_spin.value(),
                )

                self.sync_engine.disconnect()
                self.signals.finished.emit(results)

            except Exception as e:
                self.signals.error.emit(str(e))

        self.sync_thread = threading.Thread(target=run_sync, daemon=True)
        self.sync_thread.start()

    def _stop_sync(self):
        """Stop the sync process."""
        if self.sync_engine:
            self.sync_engine.stop()
            self.progress.add_log("Stop requested...", "warning")

    def _on_sync_finished(self, results: dict):
        """Handle sync completion."""
        self._is_syncing = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.source_combo.setEnabled(True)
        self.target_combo.setEnabled(True)

        self.progress.set_complete(True)
        self._refresh_stats()

        # Build summary
        sync = results.get('sync', {})
        deletes = results.get('deletes', {})

        summary_parts = []
        for model, stats in sync.items():
            summary_parts.append(
                f"{model}: {stats.get('created', 0)} created, "
                f"{stats.get('updated', 0)} updated"
            )

        for model, count in deletes.items():
            if count > 0:
                summary_parts.append(f"{model}: {count} deleted")

        if results.get('errors'):
            summary_parts.append(f"Errors: {len(results['errors'])}")

        QMessageBox.information(
            self, "Sync Complete",
            "Sync completed!\n\n" + "\n".join(summary_parts)
        )

    def _on_sync_error(self, error: str):
        """Handle sync error."""
        self._is_syncing = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.source_combo.setEnabled(True)
        self.target_combo.setEnabled(True)

        self.progress.add_log(f"Error: {error}", "error")
        QMessageBox.critical(self, "Sync Error", error)

    def closeEvent(self, event):
        """Handle dialog close."""
        if self._is_syncing:
            reply = QMessageBox.question(
                self, "Sync In Progress",
                "A sync is still running. Are you sure you want to close?\n\n"
                "The sync will be stopped.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

            self._stop_sync()

        event.accept()
