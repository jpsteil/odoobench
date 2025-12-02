"""
GUI interface for OdooBench
Full implementation from original backup_restore.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import threading
import os
from pathlib import Path
from datetime import datetime
import json
import socket
import paramiko
import configparser

from ..core.backup_restore import OdooBench
from ..db.connection_manager import ConnectionManager
from ..version import __version__

class OdooBenchGUI:
    """GUI interface for OdooBench - only loaded if tkinter is available"""

    def __init__(self, root):
        self.root = root
        self.root.title(f"OdooBench v{__version__}")
        # Let window size naturally to content
        self.root.resizable(True, True)

        # Initialize connection manager
        self.conn_manager = ConnectionManager()

        # Load configuration from database
        self.load_config()

        # Dark mode variable (load from settings)
        self.dark_mode_var = tk.BooleanVar(
            value=self.conn_manager.get_setting("dark_mode", "0") == "1"
        )

        # Apply theme
        self._apply_theme()

        # Variables
        self.source_conn = tk.StringVar()
        self.dest_conn = tk.StringVar()
        self.save_backup = tk.BooleanVar(value=False)
        self.backup_dir_path = tk.StringVar(value=self.backup_directory)

        # Create notebook for tabs
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # Create tabs
        self.create_backup_restore_tab()
        self.create_backup_files_tab()
        self.create_connections_tab()
        self.create_help_tab()

        # Auto-size window to content after all widgets are created
        self.auto_size_window()

        # Re-apply theme to all widgets after they're created
        self._apply_theme_to_widgets()

        # Check for updates in background
        self.root.after(500, self._check_for_updates)
    
    def auto_size_window(self):
        """Auto-size the window to fit its content nicely and center on primary monitor"""
        # Update the window to calculate widget sizes
        self.root.update_idletasks()
        
        # Get the required size based on content
        req_width = self.root.winfo_reqwidth()
        req_height = self.root.winfo_reqheight()
        
        # Add minimal padding for a snug fit
        width = max(req_width + 20, 900)  # Min 900 width
        height = max(req_height + 20, 650)  # Min 650 height
        
        # For multi-monitor setups, center on the primary monitor
        # First, set a default position to ensure window appears on primary monitor
        self.root.geometry(f"{width}x{height}+50+50")
        self.root.update_idletasks()
        
        # Now get the actual monitor dimensions where the window is
        # This works better for multi-monitor setups
        monitor_x = self.root.winfo_x()
        monitor_y = self.root.winfo_y()
        
        # Get the monitor's actual usable area
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # For multi-monitor, we need to estimate primary monitor size
        # Most common setup is side-by-side monitors of equal size
        if screen_width > screen_height * 2:
            # Likely multi-monitor side-by-side
            primary_width = screen_width // 2
            primary_height = screen_height
            # Center on left (primary) monitor
            x = (primary_width - width) // 2
            y = (primary_height - height) // 2
        else:
            # Single monitor or vertical setup
            x = (screen_width - width) // 2
            y = (screen_height - height) // 2
        
        # Ensure window doesn't go off-screen
        x = max(10, x)  # At least 10 pixels from edge
        y = max(10, y)
        
        # Set the geometry to center the window
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        
        # Force update to ensure centering takes effect
        self.root.update()
    
    def load_config(self):
        """Load configuration from database"""
        # Set default backup directory to ~/Documents/OdooBackups
        default_backup_dir = os.path.expanduser("~/Documents/OdooBackups")
        
        # Get backup directory from database, default to ~/Documents/OdooBackups
        self.backup_directory = self.conn_manager.get_setting('backup_directory', default_backup_dir)
        
        # Ensure the directory exists
        if not os.path.exists(self.backup_directory):
            try:
                os.makedirs(self.backup_directory, exist_ok=True)
            except Exception as e:
                # If can't create, try the default
                try:
                    os.makedirs(default_backup_dir, exist_ok=True)
                    self.backup_directory = default_backup_dir
                except:
                    # Last resort: fall back to home directory
                    self.backup_directory = os.path.expanduser("~")
                self.conn_manager.set_setting('backup_directory', self.backup_directory)
    
    def save_config(self):
        """Save configuration to database"""
        try:
            self.conn_manager.set_setting('backup_directory', self.backup_directory)
        except Exception as e:
            print(f"Error saving config: {e}")

    def _toggle_dark_mode(self):
        """Toggle dark mode on/off."""
        is_dark = self.dark_mode_var.get()
        self.conn_manager.set_setting("dark_mode", "1" if is_dark else "0")
        self._apply_theme()
        self._apply_theme_to_widgets()

    def _apply_theme(self):
        """Apply light or dark theme."""
        is_dark = self.dark_mode_var.get()
        style = ttk.Style()

        if is_dark:
            # Darcula-inspired dark theme
            bg = "#2b2b2b"
            fg = "#a9b7c6"
            bg_light = "#313335"
            bg_dark = "#1e1e1e"
            select_bg = "#214283"
            border = "#3c3f41"

            style.theme_use("clam")

            style.configure(".", background=bg, foreground=fg, fieldbackground=bg_light,
                           troughcolor=bg_dark, bordercolor=border, lightcolor=bg_light,
                           darkcolor=bg_dark, insertcolor=fg)
            style.configure("TFrame", background=bg)
            style.configure("TLabel", background=bg, foreground=fg)
            style.configure("TLabelframe", background=bg, foreground=fg)
            style.configure("TLabelframe.Label", background=bg, foreground=fg)
            style.configure("TButton", background=bg_light, foreground=fg)
            style.configure("TEntry", fieldbackground=bg_light, foreground=fg, insertcolor=fg)
            style.configure("TCombobox", fieldbackground=bg_light, foreground=fg)
            style.configure("TNotebook", background=bg, foreground=fg)
            style.configure("TNotebook.Tab", background=bg_light, foreground=fg, padding=[8, 2])
            style.configure("TPanedwindow", background=bg)
            style.configure("TScrollbar", background=bg_light, troughcolor=bg_dark)
            style.configure("Treeview", background=bg_light, foreground=fg, fieldbackground=bg_light)
            style.configure("Treeview.Heading", background=bg, foreground=fg)
            style.configure("TCheckbutton", background=bg, foreground=fg)
            style.configure("TRadiobutton", background=bg, foreground=fg)

            style.map("TButton", background=[("active", bg_light)])
            style.map("TNotebook.Tab", background=[("selected", bg), ("active", bg_light)])
            style.map("Treeview", background=[("selected", select_bg)], foreground=[("selected", fg)])
            style.map("TCombobox", fieldbackground=[("readonly", bg_light)])
            style.map("TCheckbutton", background=[("active", bg)])
            style.map("TRadiobutton", background=[("active", bg)])

            self.root.configure(bg=bg)
        else:
            # Light theme
            style.theme_use("clam")

            bg = "#d9d9d9"
            fg = "#000000"
            bg_light = "#ffffff"
            select_bg = "#4a6984"
            border = "#9e9e9e"

            style.configure(".", background=bg, foreground=fg, fieldbackground=bg_light,
                           troughcolor="#c3c3c3", bordercolor=border,
                           lightcolor="#ededed", darkcolor="#cfcfcf", insertcolor=fg)
            style.configure("TFrame", background=bg)
            style.configure("TLabel", background=bg, foreground=fg)
            style.configure("TLabelframe", background=bg, foreground=fg)
            style.configure("TLabelframe.Label", background=bg, foreground=fg)
            style.configure("TButton", background="#e1e1e1", foreground=fg)
            style.configure("TEntry", fieldbackground=bg_light, foreground=fg, insertcolor=fg)
            style.configure("TCombobox", fieldbackground=bg_light, foreground=fg)
            style.configure("TNotebook", background=bg, foreground=fg)
            style.configure("TNotebook.Tab", background="#c3c3c3", foreground=fg, padding=[8, 2])
            style.configure("TPanedwindow", background=bg)
            style.configure("TScrollbar", background="#c3c3c3", troughcolor=bg)
            style.configure("Treeview", background=bg_light, foreground=fg, fieldbackground=bg_light)
            style.configure("Treeview.Heading", background=bg, foreground=fg)
            style.configure("TCheckbutton", background=bg, foreground=fg)
            style.configure("TRadiobutton", background=bg, foreground=fg)

            style.map("TButton", background=[("active", "#ececec")])
            style.map("TNotebook.Tab", background=[("selected", bg)])
            style.map("Treeview", background=[("selected", select_bg)], foreground=[("selected", "#ffffff")])
            style.map("TCombobox", fieldbackground=[("readonly", bg_light)])

            self.root.configure(bg=bg)

    def _apply_theme_to_widgets(self):
        """Apply theme to non-ttk widgets (Text, Listbox, Menu)."""
        is_dark = self.dark_mode_var.get()

        if is_dark:
            bg = "#2b2b2b"
            fg = "#a9b7c6"
            text_bg = "#313335"
            select_bg = "#214283"
        else:
            bg = "#f0f0f0"
            fg = "#000000"
            text_bg = "#ffffff"
            select_bg = "#0078d4"

        self._configure_widgets_recursive(self.root, text_bg, fg, select_bg, bg)

    def _configure_widgets_recursive(self, widget, bg, fg, select_bg, menu_bg):
        """Recursively configure non-ttk widgets."""
        widget_class = widget.winfo_class()

        try:
            if widget_class == "Text":
                widget.configure(bg=bg, fg=fg, insertbackground=fg,
                               selectbackground=select_bg, selectforeground=fg)
            elif widget_class == "Listbox":
                widget.configure(bg=bg, fg=fg,
                               selectbackground=select_bg, selectforeground=fg)
            elif widget_class == "Menu":
                widget.configure(bg=menu_bg, fg=fg,
                               activebackground=select_bg, activeforeground=fg)
        except tk.TclError:
            pass

        for child in widget.winfo_children():
            self._configure_widgets_recursive(child, bg, fg, select_bg, menu_bg)

    def _check_for_updates(self):
        """Check for updates in background."""
        from ..version import check_for_updates, __version__

        def on_update_check(has_update, latest_version):
            if has_update:
                self.root.after(0, lambda: self._show_update_dialog(latest_version))

        check_for_updates(on_update_check)

    def _show_update_dialog(self, latest_version):
        """Show update available dialog."""
        from ..version import __version__

        result = messagebox.askyesno(
            "Update Available",
            f"A new version of OdooBench is available.\n\n"
            f"Installed: {__version__}\n"
            f"Latest: {latest_version}\n\n"
            f"Would you like to upgrade now?\n\n"
            f"(This will run: pip install --upgrade odoobench)"
        )

        if result:
            self._run_upgrade()

    def _run_upgrade(self):
        """Run pip upgrade in background."""
        import subprocess

        def do_upgrade():
            try:
                # Try pipx first, fall back to pip
                try:
                    result = subprocess.run(
                        ["pipx", "upgrade", "odoobench"],
                        capture_output=True,
                        text=True
                    )
                except FileNotFoundError:
                    # pipx not found, try pip
                    result = subprocess.run(
                        ["pip", "install", "--upgrade", "odoobench"],
                        capture_output=True,
                        text=True
                    )

                if result.returncode == 0:
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Upgrade Complete",
                        "OdooBench has been upgraded.\n\n"
                        "Please restart the application to use the new version."
                    ))
                else:
                    error = result.stderr or result.stdout or "Unknown error"
                    self.root.after(0, lambda: messagebox.showerror(
                        "Upgrade Failed",
                        f"Failed to upgrade:\n{error}"
                    ))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror(
                    "Upgrade Failed",
                    f"Failed to upgrade:\n{e}\n\n"
                    "Please upgrade manually:\n"
                    "pip install --upgrade odoobench"
                ))

        thread = threading.Thread(target=do_upgrade, daemon=True)
        thread.start()

    def _install_launcher(self):
        """Install desktop launcher for the current OS."""
        from ..launcher import create_launcher
        try:
            success = create_launcher()
            if success:
                messagebox.showinfo(
                    "Launcher Installed",
                    "Desktop launcher installed successfully.\n\n"
                    "You may need to log out and back in for it to appear."
                )
            else:
                messagebox.showwarning(
                    "Launcher Not Installed",
                    "Could not install desktop launcher for this operating system."
                )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to install launcher:\n{e}")

    def _remove_launcher(self):
        """Remove desktop launcher for the current OS."""
        from ..launcher import remove_launcher
        try:
            success = remove_launcher()
            if success:
                messagebox.showinfo(
                    "Launcher Removed",
                    "Desktop launcher removed successfully."
                )
            else:
                messagebox.showinfo(
                    "No Launcher Found",
                    "No desktop launcher was found to remove."
                )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to remove launcher:\n{e}")

    def setup_dialog_bindings(self, dialog, cancel_command=None, accept_command=None, first_field=None):
        """Setup standard keyboard bindings for dialogs
        
        Args:
            dialog: The Toplevel dialog window
            cancel_command: Function to call on Escape (defaults to dialog.destroy)
            accept_command: Function to call on Enter
            first_field: Widget to focus on when dialog opens
        """
        # Set up Escape key to cancel
        if cancel_command is None:
            cancel_command = dialog.destroy
        dialog.bind('<Escape>', lambda e: cancel_command())
        
        # Set up Enter key for default action
        if accept_command:
            dialog.bind('<Return>', lambda e: accept_command())
        
        # Focus on first field if provided
        if first_field:
            def set_focus_and_select():
                first_field.focus_set()
                # If it's an Entry widget, select all text
                if hasattr(first_field, 'select_range'):
                    first_field.select_range(0, 'end')
                elif hasattr(first_field, 'selection_range'):
                    first_field.selection_range(0, 'end')
            dialog.after(100, set_focus_and_select)
        
        # Make dialog modal
        dialog.transient(self.root)
        dialog.grab_set()

    def create_backup_restore_tab(self):
        """Create the main backup/restore tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Backup & Restore")

        # Create main container
        main_container = ttk.Frame(tab, padding="10")
        main_container.pack(fill="both", expand=True)

        # Operation Mode (moved to top)
        self.mode_frame = ttk.LabelFrame(main_container, text="Operation Mode", padding="10")
        self.mode_frame.pack(fill="x", pady=5)
        
        self.operation_mode = tk.StringVar(value="backup_restore")
        
        # Radio buttons for operation mode
        mode_options_frame = ttk.Frame(self.mode_frame)
        mode_options_frame.pack(side="left")
        
        ttk.Radiobutton(
            mode_options_frame, text="Backup & Restore", 
            variable=self.operation_mode, value="backup_restore",
            command=self.update_operation_ui
        ).pack(side="left", padx=10)
        ttk.Radiobutton(
            mode_options_frame, text="Backup Only", 
            variable=self.operation_mode, value="backup_only",
            command=self.update_operation_ui
        ).pack(side="left", padx=10)
        ttk.Radiobutton(
            mode_options_frame, text="Restore Only", 
            variable=self.operation_mode, value="restore_only",
            command=self.update_operation_ui
        ).pack(side="left", padx=10)
        
        # Backup/Restore file options (initially hidden)
        self.file_options_frame = ttk.Frame(self.mode_frame)
        self.file_options_frame.pack(side="left", padx=20)
        
        # For backup only - where to save
        self.backup_file_frame = ttk.Frame(self.file_options_frame)
        self.backup_file_var = tk.StringVar()
        ttk.Label(self.backup_file_frame, text="Save to:").pack(side="left", padx=5)
        ttk.Entry(self.backup_file_frame, textvariable=self.backup_file_var, width=40).pack(side="left", padx=5)
        ttk.Button(self.backup_file_frame, text="Browse", command=self.browse_backup_file).pack(side="left")
        
        # For restore only - file to restore from (dropdown)
        self.restore_file_frame = ttk.Frame(self.file_options_frame)
        self.restore_file_var = tk.StringVar()
        self.restore_file_mapping = {}  # Initialize mapping of filename to full path
        ttk.Label(self.restore_file_frame, text="Restore from:").pack(side="left", padx=5)
        self.restore_file_combo = ttk.Combobox(self.restore_file_frame, textvariable=self.restore_file_var, width=50)
        self.restore_file_combo.pack(side="left", padx=5)
        ttk.Button(self.restore_file_frame, text="Browse", command=self.browse_restore_file).pack(side="left")
        ttk.Button(self.restore_file_frame, text="Refresh", command=self.refresh_restore_files).pack(side="left", padx=5)

        # Source connection
        self.source_frame = ttk.LabelFrame(
            main_container, text="Source Connection", padding="10"
        )
        self.source_frame.pack(fill="x", pady=5)

        ttk.Label(self.source_frame, text="Connection:").pack(side="left", padx=5)
        self.source_combo = ttk.Combobox(
            self.source_frame, textvariable=self.source_conn, width=30
        )
        self.source_combo.pack(side="left", padx=5)
        self.source_combo.bind(
            "<<ComboboxSelected>>", lambda e: self.on_source_selected()
        )

        ttk.Button(self.source_frame, text="Refresh", command=self.refresh_connections).pack(
            side="left", padx=5
        )
        ttk.Button(
            self.source_frame, text="Test", command=lambda: self.test_connection("source")
        ).pack(side="left", padx=5)

        # Source details
        self.source_details = ttk.Frame(self.source_frame)
        self.source_details.pack(side="left", padx=20)
        self.source_info_label = ttk.Label(
            self.source_details, text="No connection selected"
        )
        self.source_info_label.pack()

        # Destination connection
        self.dest_frame = ttk.LabelFrame(
            main_container, text="Destination Connection", padding="10"
        )
        self.dest_frame.pack(fill="x", pady=5)

        ttk.Label(self.dest_frame, text="Connection:").pack(side="left", padx=5)
        self.dest_combo = ttk.Combobox(
            self.dest_frame, textvariable=self.dest_conn, width=30
        )
        self.dest_combo.pack(side="left", padx=5)
        self.dest_combo.bind(
            "<<ComboboxSelected>>", lambda e: self.on_dest_selected()
        )

        ttk.Button(
            self.dest_frame, text="Test", command=lambda: self.test_connection("dest")
        ).pack(side="left", padx=5)

        # Destination details
        self.dest_details = ttk.Frame(self.dest_frame)
        self.dest_details.pack(side="left", padx=20)
        self.dest_info_label = ttk.Label(
            self.dest_details, text="No connection selected"
        )
        self.dest_info_label.pack()

        # Options
        options_frame = ttk.LabelFrame(main_container, text="Options", padding="10")
        options_frame.pack(fill="x", pady=5)

        self.db_only = tk.BooleanVar()
        self.filestore_only = tk.BooleanVar()
        self.neutralize = tk.BooleanVar(value=True)  # Default to checked for safety

        ttk.Checkbutton(
            options_frame, text="Database Only", variable=self.db_only
        ).pack(side="left", padx=10)
        ttk.Checkbutton(
            options_frame, text="Filestore Only", variable=self.filestore_only
        ).pack(side="left", padx=10)
        
        # Neutralize option with tooltip
        neutralize_check = ttk.Checkbutton(
            options_frame, text="Neutralize (Restore Only)", variable=self.neutralize
        )
        neutralize_check.pack(side="left", padx=10)
        
        # Add tooltip to explain neutralization
        # Note: Neutralization will disable emails, crons, and set safe defaults

        # Progress
        progress_frame = ttk.Frame(main_container)
        progress_frame.pack(fill="x", pady=10)

        self.progress_label = ttk.Label(progress_frame, text="Ready")
        self.progress_label.pack(anchor="w")

        self.progress_bar = ttk.Progressbar(progress_frame, mode="determinate")
        self.progress_bar.pack(fill="x", pady=5)

        # Log - takes remaining space
        log_frame = ttk.LabelFrame(main_container, text="Output Log", padding="5")
        log_frame.pack(fill="both", expand=True, pady=5)

        # Let log expand to fill available space
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD)
        self.log_text.pack(fill="both", expand=True)

        # Configure tags for colored output
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("warning", foreground="orange")
        self.log_text.tag_config("success", foreground="green")
        self.log_text.tag_config("info", foreground="black")

        # Action buttons
        button_frame = ttk.Frame(main_container)
        button_frame.pack(pady=10)

        self.execute_btn = ttk.Button(
            button_frame,
            text="Execute Operation",
            command=self.execute_operation,
            style="Accent.TButton",
        )
        self.execute_btn.pack(side="left", padx=5)

        ttk.Button(button_frame, text="Clear Log", command=self.clear_log).pack(
            side="left", padx=5
        )
        ttk.Button(button_frame, text="Exit", command=self.root.quit).pack(
            side="left", padx=5
        )

        # Load connections
        self.refresh_connections()
        
        # Set initial UI state
        self.update_operation_ui()

    def create_connections_tab(self):
        """Create the connections management tab with separate sections"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Configuration")
        
        # Main container
        main_container = ttk.Frame(tab)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # === SETTINGS SECTION ===
        settings_frame = ttk.LabelFrame(main_container, text="Settings", padding="10")
        settings_frame.pack(fill="x", pady=(0, 10))
        
        # Backup Directory
        backup_dir_frame = ttk.Frame(settings_frame)
        backup_dir_frame.pack(fill="x", pady=5)
        
        ttk.Label(backup_dir_frame, text="Backup Directory:").pack(side="left", padx=(0, 10))
        
        self.backup_dir_var = tk.StringVar(value=self.backup_directory)
        backup_dir_entry = ttk.Entry(backup_dir_frame, textvariable=self.backup_dir_var, width=50)
        backup_dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        def browse_backup_dir():
            directory = filedialog.askdirectory(title="Select Backup Directory", initialdir=self.backup_directory)
            if directory:
                self.backup_dir_var.set(directory)
                self.backup_directory = directory
                self.save_config()
                # Update the backup files tab
                self.refresh_backup_files()
                messagebox.showinfo("Success", f"Backup directory updated to: {directory}")
        
        ttk.Button(backup_dir_frame, text="Browse", command=browse_backup_dir).pack(side="left", padx=(0, 5))
        
        def apply_backup_dir():
            directory = self.backup_dir_var.get()
            if directory and os.path.exists(directory):
                self.backup_directory = directory
                self.save_config()
                self.refresh_backup_files()
                messagebox.showinfo("Success", "Backup directory updated successfully")
            else:
                messagebox.showerror("Error", "Invalid directory path")
        
        ttk.Button(backup_dir_frame, text="Apply", command=apply_backup_dir).pack(side="left")

        # Dark Mode checkbox
        dark_mode_frame = ttk.Frame(settings_frame)
        dark_mode_frame.pack(fill="x", pady=5)

        ttk.Checkbutton(
            dark_mode_frame,
            text="Dark Mode",
            variable=self.dark_mode_var,
            command=self._toggle_dark_mode
        ).pack(side="left", padx=(0, 10))

        # Desktop Launcher buttons
        launcher_frame = ttk.Frame(settings_frame)
        launcher_frame.pack(fill="x", pady=5)

        ttk.Label(launcher_frame, text="Desktop Launcher:").pack(side="left", padx=(0, 10))
        ttk.Button(
            launcher_frame,
            text="Install Launcher",
            command=self._install_launcher
        ).pack(side="left", padx=(0, 5))
        ttk.Button(
            launcher_frame,
            text="Remove Launcher",
            command=self._remove_launcher
        ).pack(side="left")

        # Create PanedWindow for two sections
        paned = ttk.PanedWindow(main_container, orient="vertical")
        paned.pack(fill="both", expand=True)

        # === ODOO CONNECTIONS SECTION ===
        odoo_frame = ttk.LabelFrame(paned, text="Odoo Database Connections", padding="10")
        paned.add(odoo_frame, weight=1)

        # Treeview for Odoo connections
        odoo_list_frame = ttk.Frame(odoo_frame)
        odoo_list_frame.pack(fill="both", expand=True)
        
        columns = ("Host", "Port", "Database", "User", "Has SSH")
        self.odoo_tree = ttk.Treeview(
            odoo_list_frame, columns=columns, show="tree headings", height=8
        )
        self.odoo_tree.heading("#0", text="Connection Name")
        self.odoo_tree.heading("Host", text="DB Host")
        self.odoo_tree.heading("Port", text="Port")
        self.odoo_tree.heading("Database", text="Database")
        self.odoo_tree.heading("User", text="DB User")
        self.odoo_tree.heading("Has SSH", text="SSH")

        self.odoo_tree.column("#0", width=150)
        self.odoo_tree.column("Host", width=120)
        self.odoo_tree.column("Port", width=60)
        self.odoo_tree.column("Database", width=120)
        self.odoo_tree.column("User", width=100)
        self.odoo_tree.column("Has SSH", width=50)

        self.odoo_tree.pack(side="left", fill="both", expand=True)
        
        # Bind double-click event to edit Odoo connection
        self.odoo_tree.bind("<Double-Button-1>", lambda e: self.edit_odoo_connection())

        # Scrollbar for Odoo connections
        odoo_scrollbar = ttk.Scrollbar(
            odoo_list_frame, orient="vertical", command=self.odoo_tree.yview
        )
        odoo_scrollbar.pack(side="right", fill="y")
        self.odoo_tree.configure(yscrollcommand=odoo_scrollbar.set)

        # Buttons for Odoo connections
        odoo_btn_frame = ttk.Frame(odoo_frame)
        odoo_btn_frame.pack(pady=10)

        ttk.Button(
            odoo_btn_frame, text="Add Odoo Connection", command=self.add_odoo_connection_dialog
        ).pack(side="left", padx=5)
        ttk.Button(odoo_btn_frame, text="Edit", command=self.edit_odoo_connection).pack(
            side="left", padx=5
        )
        ttk.Button(odoo_btn_frame, text="Delete", command=self.delete_odoo_connection).pack(
            side="left", padx=5
        )
        ttk.Button(odoo_btn_frame, text="Test Connection", command=lambda: self.test_selected_connection("odoo")).pack(
            side="left", padx=5
        )

        # === SSH CONNECTIONS SECTION ===
        ssh_frame = ttk.LabelFrame(paned, text="SSH Server Connections", padding="10")
        paned.add(ssh_frame, weight=1)

        # Treeview for SSH connections
        ssh_list_frame = ttk.Frame(ssh_frame)
        ssh_list_frame.pack(fill="both", expand=True)
        
        ssh_columns = ("Host", "Port", "User", "Auth Type")
        self.ssh_tree = ttk.Treeview(
            ssh_list_frame, columns=ssh_columns, show="tree headings", height=8
        )
        self.ssh_tree.heading("#0", text="Connection Name")
        self.ssh_tree.heading("Host", text="SSH Host")
        self.ssh_tree.heading("Port", text="Port")
        self.ssh_tree.heading("User", text="SSH User")
        self.ssh_tree.heading("Auth Type", text="Auth")

        self.ssh_tree.column("#0", width=150)
        self.ssh_tree.column("Host", width=150)
        self.ssh_tree.column("Port", width=60)
        self.ssh_tree.column("User", width=120)
        self.ssh_tree.column("Auth Type", width=100)

        self.ssh_tree.pack(side="left", fill="both", expand=True)
        
        # Bind double-click event to edit SSH connection
        self.ssh_tree.bind("<Double-Button-1>", lambda e: self.edit_ssh_connection())

        # Scrollbar for SSH connections
        ssh_scrollbar = ttk.Scrollbar(
            ssh_list_frame, orient="vertical", command=self.ssh_tree.yview
        )
        ssh_scrollbar.pack(side="right", fill="y")
        self.ssh_tree.configure(yscrollcommand=ssh_scrollbar.set)

        # Buttons for SSH connections
        ssh_btn_frame = ttk.Frame(ssh_frame)
        ssh_btn_frame.pack(pady=10)

        ttk.Button(
            ssh_btn_frame, text="Add SSH Connection", command=self.add_ssh_connection_dialog
        ).pack(side="left", padx=5)
        ttk.Button(ssh_btn_frame, text="Edit", command=self.edit_ssh_connection).pack(
            side="left", padx=5
        )
        ttk.Button(ssh_btn_frame, text="Delete", command=self.delete_ssh_connection).pack(
            side="left", padx=5
        )
        ttk.Button(ssh_btn_frame, text="Test SSH", command=lambda: self.test_selected_connection("ssh")).pack(
            side="left", padx=5
        )

        # Load connections
        self.load_connections_list()

    def create_backup_files_tab(self):
        """Create the backup files management tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Backup Files")
        
        # Main container
        main_frame = ttk.Frame(tab, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # Header with current directory info
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(header_frame, text="Current Directory:").pack(side="left", padx=(0, 5))
        self.current_dir_label = ttk.Label(header_frame, text=os.getcwd(), font=("TkDefaultFont", 9, "bold"))
        self.current_dir_label.pack(side="left")
        
        # Files list frame
        list_frame = ttk.LabelFrame(main_frame, text="Backup Files", padding="10")
        list_frame.pack(fill="both", expand=True)
        
        # Treeview for files
        columns = ("Size", "Date Modified", "Type")
        self.files_tree = ttk.Treeview(list_frame, columns=columns, show="tree headings", height=15)
        self.files_tree.heading("#0", text="Filename")
        self.files_tree.heading("Size", text="Size")
        self.files_tree.heading("Date Modified", text="Modified")
        self.files_tree.heading("Type", text="Type")
        
        self.files_tree.column("#0", width=350)
        self.files_tree.column("Size", width=100)
        self.files_tree.column("Date Modified", width=150)
        self.files_tree.column("Type", width=100)
        
        # Scrollbars
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.files_tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal", command=self.files_tree.xview)
        self.files_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Grid layout for treeview and scrollbars
        self.files_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        
        # Bind double-click to view file details
        self.files_tree.bind("<Double-Button-1>", self.view_backup_file_details)
        
        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Button(button_frame, text="Refresh", command=self.refresh_backup_files).pack(side="left", padx=5)
        ttk.Button(button_frame, text="View Details", command=self.view_selected_backup_details).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Delete", command=self.delete_selected_backup).pack(side="left", padx=5)
        
        # Stats frame
        stats_frame = ttk.Frame(main_frame)
        stats_frame.pack(fill="x", pady=(10, 0))
        
        self.backup_stats_label = ttk.Label(stats_frame, text="", font=("TkDefaultFont", 9))
        self.backup_stats_label.pack(side="left")
        
        # Initial load
        self.refresh_backup_files()

    def refresh_backup_files(self):
        """Refresh the list of backup files in the backup directory"""
        # Clear existing items
        for item in self.files_tree.get_children():
            self.files_tree.delete(item)
        
        # Use configured backup directory
        current_dir = self.backup_directory
        self.current_dir_label.config(text=current_dir)
        
        # Look for backup files (tar.gz files)
        backup_files = []
        total_size = 0
        
        try:
            for file in os.listdir(current_dir):
                if file.endswith('.tar.gz') or file.endswith('.tgz') or file.endswith('.zip'):
                    file_path = os.path.join(current_dir, file)
                    if os.path.isfile(file_path):
                        stat = os.stat(file_path)
                        size = stat.st_size
                        total_size += size
                        mtime = datetime.fromtimestamp(stat.st_mtime)
                        
                        # Determine type based on filename pattern
                        file_type = "Unknown"
                        if "_backup_" in file or "_restore_" in file:
                            file_type = "Odoo Backup"
                        elif "filestore" in file.lower():
                            file_type = "Filestore"
                        elif "database" in file.lower() or "db" in file.lower():
                            file_type = "Database"
                        
                        backup_files.append({
                            'name': file,
                            'path': file_path,
                            'size': size,
                            'mtime': mtime,
                            'type': file_type
                        })
            
            # Sort by modification time (newest first)
            backup_files.sort(key=lambda x: x['mtime'], reverse=True)
            
            # Add to tree
            for backup in backup_files:
                size_str = self.format_file_size(backup['size'])
                date_str = backup['mtime'].strftime("%Y-%m-%d %H:%M:%S")
                
                self.files_tree.insert('', 'end', text=backup['name'],
                                      values=(size_str, date_str, backup['type']),
                                      tags=(backup['path'],))
            
            # Update stats
            total_size_str = self.format_file_size(total_size)
            self.backup_stats_label.config(text=f"Total: {len(backup_files)} backup files, {total_size_str}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to list backup files: {str(e)}")
    
    def format_file_size(self, size):
        """Format file size in human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} TB"
    
    def view_backup_file_details(self, event=None):
        """View details of a backup file"""
        self.view_selected_backup_details()
    
    def view_selected_backup_details(self):
        """View details of the selected backup file"""
        selection = self.files_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a backup file to view details.")
            return
        
        item = self.files_tree.item(selection[0])
        filename = item['text']
        file_path = item['tags'][0] if item['tags'] else None
        
        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("Error", "File not found.")
            return
        
        try:
            # Open file with the system's default application
            import platform
            import subprocess
            
            if platform.system() == 'Darwin':       # macOS
                subprocess.call(('open', file_path))
            elif platform.system() == 'Windows':    # Windows
                os.startfile(file_path)
            else:                                   # Linux and others
                subprocess.call(('xdg-open', file_path))
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open backup file: {str(e)}")
    
    def delete_selected_backup(self):
        """Delete the selected backup file"""
        selection = self.files_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a backup file to delete.")
            return
        
        item = self.files_tree.item(selection[0])
        filename = item['text']
        file_path = item['tags'][0] if item['tags'] else None
        
        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("Error", "File not found.")
            return
        
        # Confirm deletion
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{filename}'?\n\nThis action cannot be undone."):
            try:
                os.remove(file_path)
                messagebox.showinfo("Success", f"File '{filename}' has been deleted.")
                self.refresh_backup_files()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete file: {str(e)}")
    
    def create_help_tab(self):
        """Create the Help tab with documentation"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Help")
        
        # Create scrollable text widget
        main_frame = ttk.Frame(tab, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # Create text widget with scrollbar
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill="both", expand=True)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side="right", fill="y")
        
        # Text widget
        help_text = tk.Text(text_frame, wrap="word", yscrollcommand=scrollbar.set, 
                           font=("TkDefaultFont", 10), padx=10, pady=10)
        help_text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=help_text.yview)
        
        # Add help content
        help_content = """
ODOO BACKUP MANAGER - HELP GUIDE
=================================

OVERVIEW
--------
This tool provides comprehensive backup and restore capabilities for Odoo databases and filestores.
It features a smart interface that automatically launches the GUI when available, or falls back to CLI mode.

INTERFACE MODES (v1.1.0+)
-------------------------
The application intelligently detects your environment:
• GUI Mode: Launches automatically when display and tkinter are available
• CLI Mode: Used in SSH sessions, Docker containers, or when explicitly requested

Launch Options:
• odoo-backup          - Smart mode (GUI if available, otherwise help)
• odoo-backup --gui    - Force GUI mode (error if unavailable)
• odoo-backup --cli    - Force CLI mode

CLI USAGE
---------
For automation, scripts, or remote access, use CLI mode:

Connection Management:
• odoo-backup --cli connections save --name prod --host db.example.com --user odoo
• odoo-backup --cli connections list
• odoo-backup --cli connections delete prod

Backup Operations:
• odoo-backup --cli backup --connection prod
• odoo-backup --cli backup --name mydb --host localhost --user odoo

Restore Operations:
• odoo-backup --cli restore --connection dev --file backup.tar.gz --name test_db
• odoo-backup --cli restore --connection dev --file backup.tar.gz --neutralize

OPERATION MODES
---------------
• Backup & Restore: Copy data from source to destination in one operation
• Backup Only: Create a backup archive file (.tar.gz)
• Restore Only: Restore from an existing backup archive

DATABASE NEUTRALIZATION
-----------------------
When restoring a database, you can enable the "Neutralize" option to make it safe for testing.
This feature is crucial when restoring production data to test/development environments.

What Gets Neutralized:
• All outgoing mail servers - Disabled to prevent sending emails
• All scheduled actions (crons) - Disabled to prevent automated tasks
• Payment acquirers - Disabled to prevent payment processing
• Email queue - Cleared of any pending/failed emails
• Website indexing - Robots.txt set to disallow all crawlers
• Company names - Prefixed with [TEST] to identify as test environment
• Base URL - Unfrozen to allow configuration changes

⚠️ WARNING: Neutralization modifies the database. Only use on test/development systems!

CONNECTIONS
-----------
Database Connections:
• Configure PostgreSQL connection details
• Test connections before operations
• Set filestore paths for complete backups
• Mark connections as "Allow Restore" to enable restore operations

SSH Connections:
• Configure SSH access for remote servers
• Use SSH key authentication (recommended) or password
• Required for remote filestore operations

Production Safety:
• Connections are protected from restore by default
• Must explicitly enable "Allow Restore" for non-production connections
• CLI respects the same safety settings as GUI

BACKUP FILES
------------
• View all backup files in your configured directory
• Double-click to view backup details
• Delete old backups to save space
• Files are named with timestamp: backup_DBNAME_YYYYMMDD_HHMMSS.tar.gz

BACKUP STRUCTURE
----------------
Each backup archive contains:
• database.sql - PostgreSQL dump of the database
• filestore.tar.gz - Compressed Odoo filestore (if included)
• metadata.json - Backup information and version details

AUTOMATION
----------
Schedule backups using cron:
0 2 * * * /usr/local/bin/odoo-backup --cli backup --connection prod

Use in Docker containers:
docker run -it myimage odoo-backup --cli backup --connection prod

Script multiple databases:
for DB in db1 db2 db3; do
    odoo-backup --cli backup --connection prod --name "$DB"
done

BEST PRACTICES
--------------
1. Always test connections before running operations
2. Enable "Neutralize" when restoring to non-production environments
3. Keep regular backups and test restore procedures
4. Use SSH keys instead of passwords for remote connections
5. Monitor available disk space before large operations
6. Verify Odoo version compatibility when restoring
7. Use connection profiles instead of manual parameters
8. Protect production connections (disable restore)

TROUBLESHOOTING
---------------
GUI Not Launching:
• Check DISPLAY environment variable: echo $DISPLAY
• Install tkinter: sudo apt-get install python3-tk
• Use CLI mode as fallback: odoo-backup --cli

Connection Failed:
• Verify host, port, and credentials
• Check network connectivity
• Ensure PostgreSQL is accepting connections
• For SSH: verify key permissions (600)

Backup Failed:
• Check disk space on backup destination
• Verify database and filestore paths
• Ensure proper permissions

Restore Failed:
• Confirm target database doesn't exist or can be dropped
• Check available disk space
• Verify backup file integrity
• Ensure matching Odoo versions
• Check if connection allows restore operations

KEYBOARD SHORTCUTS
------------------
• F5 - Refresh connections/files lists
• Delete - Remove selected item (with confirmation)
• Enter - View details of selected item

SAFETY FEATURES
---------------
• Connections must explicitly allow restore operations
• Confirmation dialogs for destructive operations
• Progress indication for long-running tasks
• Detailed logging of all operations
• Automatic backup file verification
• Smart GUI/CLI detection prevents errors

For more information or to report issues, visit:
https://github.com/jpsteil/odoo-backup-manager
"""
        
        help_text.insert("1.0", help_content)
        
        # Make text read-only
        help_text.config(state="disabled")
        
        # Configure tags for formatting
        help_text.tag_configure("heading", font=("TkDefaultFont", 12, "bold"))
        help_text.tag_configure("subheading", font=("TkDefaultFont", 10, "bold"))
        help_text.tag_configure("warning", foreground="orange", font=("TkDefaultFont", 10, "bold"))
        
        # Apply formatting tags (in disabled state we need to temporarily enable)
        help_text.config(state="normal")
        
        # Apply heading tags
        for pattern in ["ODOO BACKUP MANAGER - HELP GUIDE", "OVERVIEW", "INTERFACE MODES", 
                       "CLI USAGE", "OPERATION MODES", "DATABASE NEUTRALIZATION", 
                       "CONNECTIONS", "BACKUP FILES", "BACKUP STRUCTURE", "AUTOMATION",
                       "BEST PRACTICES", "TROUBLESHOOTING", "KEYBOARD SHORTCUTS", "SAFETY FEATURES"]:
            start = "1.0"
            while True:
                pos = help_text.search(pattern, start, stopindex="end")
                if not pos:
                    break
                end = f"{pos}+{len(pattern)}c"
                help_text.tag_add("heading" if pattern == "ODOO BACKUP MANAGER - HELP GUIDE" else "subheading", pos, end)
                start = end
        
        # Apply warning tag
        start = "1.0"
        pos = help_text.search("⚠️ WARNING:", start, stopindex="end")
        if pos:
            end = help_text.search("\n", pos, stopindex="end")
            help_text.tag_add("warning", pos, end)
        
        help_text.config(state="disabled")
    
    def add_odoo_connection_dialog(self):
        """Show dialog to add a new Odoo database connection"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Odoo Database Connection")
        
        # Make dialog modal
        dialog.transient(self.root)
        dialog.resizable(False, False)
        
        # Main container with padding
        main_frame = ttk.Frame(dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Connection fields dictionary
        fields = {}
        
        # Load button at top
        ttk.Button(
            main_frame,
            text="Load from odoo.conf",
            command=lambda: self.load_from_odoo_conf(fields),
        ).pack(pady=(0, 15))
        
        # Connection Details Frame
        details_frame = ttk.LabelFrame(main_frame, text="Connection Details", padding="10")
        details_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Form fields
        row = 0
        for label, field_name, default, width in [
            ("Connection Name:", "name", "", 30),
            ("Host:", "host", "localhost", 30),
            ("Port:", "port", "5432", 30),
            ("Database:", "database", "", 30),
            ("Username:", "username", "odoo", 30),
            ("Password:", "password", "", 30),
        ]:
            ttk.Label(details_frame, text=label).grid(row=row, column=0, sticky="e", padx=(0, 10), pady=5)
            entry = ttk.Entry(details_frame, width=width)
            if field_name == "password":
                entry.config(show="*")
            entry.insert(0, default)
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            fields[field_name] = entry
            row += 1
        
        # Filestore Path with Browse button
        ttk.Label(details_frame, text="Filestore Path:").grid(row=row, column=0, sticky="e", padx=(0, 10), pady=5)
        path_frame = ttk.Frame(details_frame)
        path_frame.grid(row=row, column=1, sticky="ew", pady=5)
        fields["filestore_path"] = ttk.Entry(path_frame, width=22)
        # Set default filestore path for Odoo 17
        import os
        default_filestore = os.path.expanduser("~/.local/share/Odoo")
        fields["filestore_path"].insert(0, default_filestore)
        fields["filestore_path"].pack(side=tk.LEFT, fill=tk.X, expand=True)
        fields["browse_button"] = ttk.Button(
            path_frame,
            text="Browse",
            command=lambda: self.browse_folder_entry(fields["filestore_path"]),
            width=8
        )
        fields["browse_button"].pack(side=tk.LEFT, padx=(5, 0))
        row += 1
        
        # Odoo Version
        ttk.Label(details_frame, text="Odoo Version:").grid(row=row, column=0, sticky="e", padx=(0, 10), pady=5)
        fields["odoo_version"] = ttk.Combobox(
            details_frame, width=28, values=["18.0", "17.0", "16.0", "15.0", "14.0", "13.0", "12.0"]
        )
        fields["odoo_version"].grid(row=row, column=1, sticky="ew", pady=5)
        fields["odoo_version"].set("17.0")
        row += 1
        
        # Local Development checkbox
        fields["is_local"] = tk.BooleanVar()
        ttk.Checkbutton(
            details_frame, text="Local Development Connection", variable=fields["is_local"]
        ).grid(row=row, column=1, sticky="w", pady=5)
        row += 1
        
        # Allow Restore checkbox (default to False for safety)
        fields["allow_restore"] = tk.BooleanVar(value=False)
        allow_restore_check = ttk.Checkbutton(
            details_frame, 
            text="Allow Restore Operations (⚠️ Be careful with production databases!)", 
            variable=fields["allow_restore"]
        )
        allow_restore_check.grid(row=row, column=1, sticky="w", pady=5)
        # Change checkbox color to indicate danger
        allow_restore_check.configure(style="Danger.TCheckbutton")
        
        # Configure column to expand
        details_frame.columnconfigure(1, weight=1)
        
        # SSH Options Frame
        ssh_frame = ttk.LabelFrame(main_frame, text="Remote Server Access", padding="10")
        ssh_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Define toggle function first
        def toggle_ssh_dropdown():
            """Enable/disable SSH connection dropdown and browse button based on checkbox"""
            if fields["use_ssh"].get():
                # SSH enabled - enable dropdown, disable browse button
                fields["ssh_connection"].config(state="readonly")
                fields["browse_button"].config(state="disabled")
            else:
                # SSH disabled - disable dropdown, enable browse button
                fields["ssh_connection"].config(state="disabled")
                fields["browse_button"].config(state="normal")
        
        fields["use_ssh"] = tk.BooleanVar()
        ssh_check = ttk.Checkbutton(
            ssh_frame, 
            text="Use SSH connection for remote server access", 
            variable=fields["use_ssh"],
            command=toggle_ssh_dropdown
        )
        ssh_check.pack(anchor="w", pady=(0, 5))
        
        # SSH Connection Dropdown
        ssh_select_frame = ttk.Frame(ssh_frame)
        ssh_select_frame.pack(fill=tk.X)
        
        ttk.Label(ssh_select_frame, text="SSH Connection:").pack(side=tk.LEFT, padx=(20, 10))
        
        # Get list of SSH connections
        ssh_connections = []
        ssh_connection_map = {}  # Map names to IDs
        all_connections = self.conn_manager.list_connections()
        for conn in all_connections:
            if conn['type'] == "ssh":
                ssh_connections.append(conn['name'])
                ssh_connection_map[conn['name']] = conn['id']
        
        fields["ssh_connection"] = ttk.Combobox(
            ssh_select_frame, width=30, values=ssh_connections, state="disabled"
        )
        fields["ssh_connection"].pack(side=tk.LEFT, fill=tk.X, expand=True)
        if ssh_connections:
            fields["ssh_connection"].set(ssh_connections[0])
        
        # Button frame at bottom
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        def save_connection():
            config = {
                "connection_type": "odoo",
                "host": fields["host"].get(),
                "port": int(fields["port"].get() or 5432),
                "database": fields["database"].get(),
                "username": fields["username"].get(),
                "password": fields["password"].get(),
                "filestore_path": fields["filestore_path"].get(),
                "odoo_version": fields["odoo_version"].get(),
                "is_local": fields["is_local"].get(),
                "allow_restore": fields["allow_restore"].get(),  # Include allow_restore flag
                "use_ssh": fields["use_ssh"].get(),
            }
            
            # If SSH is enabled, find the SSH connection ID
            if fields["use_ssh"].get() and fields["ssh_connection"].get():
                selected_ssh_name = fields["ssh_connection"].get()
                if selected_ssh_name in ssh_connection_map:
                    config["ssh_connection_id"] = ssh_connection_map[selected_ssh_name]
                    config["ssh_connection_name"] = selected_ssh_name
            else:
                config["ssh_connection_id"] = None
                config["ssh_connection_name"] = ""

            name = fields["name"].get()
            if not name:
                messagebox.showerror("Error", "Connection name is required")
                return

            if self.conn_manager.save_connection(name, config):
                dialog.destroy()
                self.load_connections_list()
                self.refresh_connections()
            else:
                messagebox.showerror("Error", "Failed to save connection")
        
        # Center the buttons
        ttk.Button(button_frame, text="Test Connection", 
                  command=lambda: self.test_connection_config(fields)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Save", command=save_connection).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        # Center dialog on parent after it's built
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Setup keyboard bindings and focus
        self.setup_dialog_bindings(dialog, 
                                 cancel_command=dialog.destroy,
                                 accept_command=save_connection,
                                 first_field=fields.get("name"))

    def load_from_odoo_conf(self, fields):
        """Load connection settings from odoo.conf file - local or remote based on SSH checkbox"""
        # Check if SSH is enabled
        if fields.get("use_ssh") and fields["use_ssh"].get():
            # Load from remote via SSH
            self.load_from_remote_odoo_conf(fields)
        else:
            # Load from local file
            conf_file = filedialog.askopenfilename(
                title="Select odoo.conf file",
                filetypes=[("Config files", "*.conf"), ("All files", "*.*")]
            )
            
            if not conf_file:
                return
            
            try:
                # Parse the config file
                config = OdooBench.parse_odoo_conf(conf_file)
                
                # Update the form fields
                fields["host"].delete(0, tk.END)
                fields["host"].insert(0, config["host"])
                
                fields["port"].delete(0, tk.END)
                fields["port"].insert(0, config["port"])
                
                if config["database"]:
                    fields["database"].delete(0, tk.END)
                    fields["database"].insert(0, config["database"])
                
                fields["username"].delete(0, tk.END)
                fields["username"].insert(0, config["username"])
                
                if config["password"]:
                    fields["password"].delete(0, tk.END)
                    fields["password"].insert(0, config["password"])
                
                if config["filestore_path"]:
                    fields["filestore_path"].delete(0, tk.END)
                    fields["filestore_path"].insert(0, config["filestore_path"])
                
                fields["odoo_version"].set(config["odoo_version"])
                fields["is_local"].set(config["is_local"])
                
                # Suggest a connection name based on the config file
                if not fields["name"].get():
                    config_name = os.path.basename(conf_file).replace('.conf', '')
                    fields["name"].delete(0, tk.END)
                    fields["name"].insert(0, config_name)
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load config: {str(e)}")
    
    def load_from_remote_odoo_conf(self, fields):
        """Load connection settings from a remote odoo.conf file via SSH"""
        # Check if SSH connection is already selected
        pre_selected_ssh = None
        if fields.get("use_ssh") and fields["use_ssh"].get() and fields.get("ssh_connection"):
            pre_selected_ssh = fields["ssh_connection"].get()
        
        # Create dialog
        ssh_dialog = tk.Toplevel(self.root)
        ssh_dialog.title("Load Remote odoo.conf")
        
        ssh_fields = {}
        
        # If SSH connection is pre-selected, only ask for config path
        if pre_selected_ssh:
            ssh_dialog.geometry("400x100")
            # Center dialog
            self.root.update_idletasks()
            x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 200
            y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 50
            ssh_dialog.geometry(f"400x100+{x}+{y}")
            
            ssh_dialog.transient(self.root)
            ssh_dialog.grab_set()
            
            # Store the pre-selected connection
            ssh_fields["connection"] = tk.StringVar(value=pre_selected_ssh)
            
            row = 0
            ttk.Label(ssh_dialog, text="Config Path:").grid(row=row, column=0, sticky="e", padx=5, pady=5)
            ssh_fields["config_path"] = ttk.Entry(ssh_dialog, width=25)
            ssh_fields["config_path"].grid(row=row, column=1, padx=5, pady=5)
            ssh_fields["config_path"].insert(0, "/home/administrator/qlf/odoo/odoo.conf")
            
            # Add buttons for pre-selected case
            btn_frame = ttk.Frame(ssh_dialog)
            btn_frame.grid(row=1, column=0, columnspan=2, pady=20)
            
            ttk.Button(btn_frame, text="Connect & Load", 
                      command=lambda: connect_and_load()).pack(side="left", padx=5)
            ttk.Button(btn_frame, text="Cancel", 
                      command=ssh_dialog.destroy).pack(side="left", padx=5)
        else:
            # No pre-selected SSH, show both fields
            ssh_dialog.geometry("400x150")
            # Center dialog
            self.root.update_idletasks()
            x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 200
            y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 75
            ssh_dialog.geometry(f"400x150+{x}+{y}")
            
            ssh_dialog.transient(self.root)
            ssh_dialog.grab_set()
            
            # Get list of SSH connections
            ssh_connections = []
            all_connections = self.conn_manager.list_connections()
            for conn in all_connections:
                if conn['type'] == "ssh":
                    ssh_connections.append(conn['name'])
            
            if not ssh_connections:
                messagebox.showerror("Error", "No SSH connections found. Please add an SSH connection first.")
                ssh_dialog.destroy()
                return
            
            row = 0
            ttk.Label(ssh_dialog, text="SSH Connection:").grid(row=row, column=0, sticky="e", padx=5, pady=5)
            ssh_fields["connection"] = ttk.Combobox(ssh_dialog, width=25, values=ssh_connections, state="readonly")
            ssh_fields["connection"].grid(row=row, column=1, padx=5, pady=5)
            ssh_fields["connection"].set(ssh_connections[0])
            
            row += 1
            ttk.Label(ssh_dialog, text="Config Path:").grid(row=row, column=0, sticky="e", padx=5, pady=5)
            ssh_fields["config_path"] = ttk.Entry(ssh_dialog, width=25)
            ssh_fields["config_path"].grid(row=row, column=1, padx=5, pady=5)
            ssh_fields["config_path"].insert(0, "/home/administrator/qlf/odoo/odoo.conf")
            
            # Add buttons for non-pre-selected case
            btn_frame = ttk.Frame(ssh_dialog)
            btn_frame.grid(row=row + 1, column=0, columnspan=2, pady=20)
            
            ttk.Button(btn_frame, text="Connect & Load", 
                      command=lambda: connect_and_load()).pack(side="left", padx=5)
            ttk.Button(btn_frame, text="Cancel", 
                      command=ssh_dialog.destroy).pack(side="left", padx=5)
        
        def connect_and_load():
            try:
                # Get selected SSH connection
                if isinstance(ssh_fields["connection"], tk.StringVar):
                    selected_ssh_name = ssh_fields["connection"].get()
                else:
                    selected_ssh_name = ssh_fields["connection"].get()
                # Find the SSH connection by name
                connections = self.conn_manager.list_connections()
                ssh_conn_id = None
                for conn in connections:
                    if conn['type'] == 'ssh' and conn['name'] == selected_ssh_name:
                        ssh_conn_id = conn['id']
                        break
                
                if not ssh_conn_id:
                    messagebox.showerror("Error", f"SSH connection '{selected_ssh_name}' not found")
                    return
                
                ssh_conn = self.conn_manager.get_ssh_connection(ssh_conn_id)
                if not ssh_conn:
                    messagebox.showerror("Error", f"SSH connection '{selected_ssh_name}' not found")
                    return
                
                # Create SSH client
                ssh = None
                try:
                    ssh = paramiko.SSHClient()
                    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    
                    # Connect using selected connection
                    connect_params = {
                        "hostname": ssh_conn.get("host"),
                        "port": ssh_conn.get("port", 22),
                        "username": ssh_conn.get("username"),
                        "timeout": 10,
                        "banner_timeout": 10,
                        "auth_timeout": 10
                    }
                    
                    if ssh_conn.get("ssh_key_path"):
                        connect_params["key_filename"] = ssh_conn.get("ssh_key_path")
                    elif ssh_conn.get("password"):
                        connect_params["password"] = ssh_conn.get("password")
                    
                    ssh.connect(**connect_params)
                except Exception as e:
                    messagebox.showerror("SSH Connection Failed", f"Failed to connect to SSH server: {str(e)}")
                    if ssh:
                        ssh.close()
                    return
                
                # Read the config file
                sftp = ssh.open_sftp()
                config_path = ssh_fields["config_path"].get()
                
                with sftp.open(config_path, 'r') as remote_file:
                    config_content = remote_file.read().decode('utf-8')
                
                # Get user's home directory while SSH is still connected
                stdin, stdout, stderr = ssh.exec_command('echo $HOME')
                user_home = stdout.read().decode('utf-8').strip()
                
                sftp.close()
                ssh.close()
                
                # Parse the config
                config_parser = configparser.ConfigParser()
                config_parser.read_string(config_content)
                
                if 'options' not in config_parser:
                    raise ValueError("No 'options' section found in config file")
                
                options = config_parser['options']
                
                # Update form fields
                fields["host"].delete(0, tk.END)
                fields["host"].insert(0, options.get('db_host', 'localhost'))
                
                fields["port"].delete(0, tk.END)
                fields["port"].insert(0, options.get('db_port', '5432'))
                
                if options.get('db_name') and options.get('db_name') != 'False':
                    fields["database"].delete(0, tk.END)
                    fields["database"].insert(0, options.get('db_name'))
                
                fields["username"].delete(0, tk.END)
                fields["username"].insert(0, options.get('db_user', 'odoo'))
                
                if options.get('db_password') and options.get('db_password') != 'False':
                    fields["password"].delete(0, tk.END)
                    fields["password"].insert(0, options.get('db_password'))
                
                # Set SSH connection
                fields["use_ssh"].set(True)
                # Enable SSH dropdown
                if "ssh_connection" in fields:
                    fields["ssh_connection"].config(state="readonly")
                    fields["ssh_connection"].set(selected_ssh_name)
                
                # Get filestore path from config
                data_dir = options.get('data_dir')
                db_name = options.get('db_name', '')
                
                if data_dir and data_dir != 'False':
                    # Use data_dir EXACTLY as specified in config - DO NOT append anything
                    filestore_path = data_dir
                else:
                    # No data_dir in config, use user's home directory (already retrieved)
                    # Use user's home directory for default filestore path
                    if db_name and db_name != 'False':
                        filestore_path = f"{user_home}/.local/share/Odoo/filestore/{db_name}"
                    else:
                        filestore_path = f"{user_home}/.local/share/Odoo/filestore"
                
                fields["filestore_path"].delete(0, tk.END)
                fields["filestore_path"].insert(0, filestore_path)
                
                ssh_dialog.destroy()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load remote config: {str(e)}")
    
    def test_connection_config(self, fields):
        """Test connection from config fields"""
        # First test SSH connection if enabled
        if fields.get("use_ssh") and fields["use_ssh"].get():
            # Get selected SSH connection from dropdown
            selected_ssh = fields.get("ssh_connection")
            if not selected_ssh or not selected_ssh.get():
                messagebox.showerror("Error", "Please select an SSH connection")
                return
            
            # Find SSH connection by name
            selected_ssh_name = selected_ssh.get()
            connections = self.conn_manager.list_connections()
            ssh_conn_id = None
            for conn in connections:
                if conn['type'] == 'ssh' and conn['name'] == selected_ssh_name:
                    ssh_conn_id = conn['id']
                    break
            
            if not ssh_conn_id:
                messagebox.showerror("Error", f"SSH connection '{selected_ssh_name}' not found")
                return
                
            ssh_conn = self.conn_manager.get_ssh_connection(ssh_conn_id)
            if not ssh_conn:
                messagebox.showerror("Error", f"SSH connection '{selected_ssh_name}' not found")
                return
            
            try:
                # Test SSH connection
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                # Connect with password or key
                connect_kwargs = {
                    "hostname": ssh_conn.get("host"),
                    "port": ssh_conn.get("port", 22),
                    "username": ssh_conn.get("username"),
                    "timeout": 10,
                    "banner_timeout": 10,
                    "auth_timeout": 10
                }
                
                if ssh_conn.get("ssh_key_path") and os.path.exists(ssh_conn.get("ssh_key_path")):
                    connect_kwargs["key_filename"] = ssh_conn.get("ssh_key_path")
                elif ssh_conn.get("password"):
                    connect_kwargs["password"] = ssh_conn.get("password")
                else:
                    messagebox.showerror("Error", "SSH password or key file is required")
                    return
                
                ssh.connect(**connect_kwargs)
                
                # Test if we can execute a simple command
                stdin, stdout, stderr = ssh.exec_command("echo 'SSH connection successful'")
                stdout.read()
                
                ssh.close()
                
                # Now test database connection through SSH tunnel
                messagebox.showinfo("Success", "SSH connection successful! Testing database connection...")
                
            except Exception as e:
                messagebox.showerror("Error", f"SSH connection failed: {str(e)}")
                return
        
        # Test database connection
        # Find SSH connection ID if SSH is enabled
        ssh_conn_id = None
        if fields.get("use_ssh") and fields["use_ssh"].get() and fields.get("ssh_connection"):
            selected_ssh_name = fields["ssh_connection"].get()
            if selected_ssh_name:
                connections = self.conn_manager.list_connections()
                for conn in connections:
                    if conn['type'] == 'ssh' and conn['name'] == selected_ssh_name:
                        ssh_conn_id = conn['id']
                        break
        
        config = {
            "db_host": fields["host"].get(),
            "db_port": int(fields["port"].get() or 5432),
            "db_user": fields["username"].get(),
            "db_password": fields["password"].get(),
            "db_name": fields["database"].get(),
            "filestore_path": fields["filestore_path"].get() if fields.get("filestore_path") else None,
            "use_ssh": fields.get("use_ssh", {}).get() if fields.get("use_ssh") else False,
            "ssh_connection_id": ssh_conn_id
        }

        tool = OdooBench(conn_manager=self.conn_manager)
        success, msg = tool.test_connection(config)

        messagebox.showinfo("Test Results", msg)

    def browse_folder_entry(self, entry):
        """Browse for folder and set entry value"""
        folder = filedialog.askdirectory()
        if folder:
            entry.delete(0, tk.END)
            entry.insert(0, folder)
    
    def browse_file_entry(self, entry):
        """Browse for file and set entry value"""
        file_path = filedialog.askopenfilename(
            title="Select SSH Key File",
            filetypes=[("All files", "*.*"), ("PEM files", "*.pem"), ("Key files", "*.key")]
        )
        if file_path:
            entry.delete(0, tk.END)
            entry.insert(0, file_path)

    def load_connections_list(self):
        """Load connections into both treeviews using IDs"""
        connections = self.conn_manager.list_connections()
        
        # Load Odoo connections if tree exists
        if hasattr(self, 'odoo_tree'):
            # Clear existing items
            for item in self.odoo_tree.get_children():
                self.odoo_tree.delete(item)
            
            # Load Odoo connections
            for conn in connections:
                if conn['type'] == 'odoo':
                    # Get full details using ID
                    conn_details = self.conn_manager.get_odoo_connection(conn['id'])
                    if conn_details:
                        has_ssh = "Yes" if conn_details.get("use_ssh") else "No"
                        # Store the ID in the tree item
                        item_id = self.odoo_tree.insert(
                            "", "end", text=conn['name'],
                            values=(
                                conn_details.get("host", ""),
                                conn_details.get("port", "5432"),
                                conn_details.get("database", ""),
                                conn_details.get("username", ""),
                                has_ssh
                            ),
                            tags=(str(conn['id']),)  # Store ID in tags
                        )
        
        # Load SSH connections if tree exists
        if hasattr(self, 'ssh_tree'):
            # Clear existing items
            for item in self.ssh_tree.get_children():
                self.ssh_tree.delete(item)
            
            # Load SSH connections
            for conn in connections:
                if conn['type'] == 'ssh':
                    # Get full details using ID
                    conn_details = self.conn_manager.get_ssh_connection(conn['id'])
                    if conn_details:
                        auth_type = "Key" if conn_details.get("ssh_key_path") else "Password"
                        item_id = self.ssh_tree.insert(
                            "", "end", text=conn['name'],
                            values=(
                                conn_details.get("host", ""),
                                conn_details.get("port", "22"),
                                conn_details.get("username", ""),
                                auth_type
                            ),
                            tags=(str(conn['id']),)  # Store ID in tags
                        )

    def add_ssh_connection_dialog(self):
        """Show dialog to add a new SSH connection"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Add SSH Connection")
        dialog.geometry("400x350")
        
        # Center dialog
        self.root.update_idletasks()
        width = 400
        height = 350
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (width // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (height // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        
        fields = {}
        row = 0
        
        ttk.Label(dialog, text="Connection Name:").grid(row=row, column=0, sticky="e", padx=5, pady=5)
        fields["name"] = ttk.Entry(dialog, width=25)
        fields["name"].grid(row=row, column=1, padx=5, pady=5)
        
        row += 1
        ttk.Label(dialog, text="SSH Host:").grid(row=row, column=0, sticky="e", padx=5, pady=5)
        fields["host"] = ttk.Entry(dialog, width=25)
        fields["host"].grid(row=row, column=1, padx=5, pady=5)
        
        row += 1
        ttk.Label(dialog, text="SSH Port:").grid(row=row, column=0, sticky="e", padx=5, pady=5)
        fields["port"] = ttk.Entry(dialog, width=25)
        fields["port"].grid(row=row, column=1, padx=5, pady=5)
        fields["port"].insert(0, "22")
        
        row += 1
        ttk.Label(dialog, text="SSH User:").grid(row=row, column=0, sticky="e", padx=5, pady=5)
        fields["user"] = ttk.Entry(dialog, width=25)
        fields["user"].grid(row=row, column=1, padx=5, pady=5)
        
        row += 1
        ttk.Label(dialog, text="Authentication:").grid(row=row, column=0, sticky="e", padx=5, pady=5)
        auth_frame = ttk.Frame(dialog)
        auth_frame.grid(row=row, column=1, padx=5, pady=5)
        
        auth_var = tk.StringVar(value="password")
        ttk.Radiobutton(auth_frame, text="Password", variable=auth_var, value="password").pack(side="left")
        ttk.Radiobutton(auth_frame, text="Key File", variable=auth_var, value="key").pack(side="left")
        fields["auth_type"] = auth_var
        
        row += 1
        ttk.Label(dialog, text="Password:").grid(row=row, column=0, sticky="e", padx=5, pady=5)
        fields["password"] = ttk.Entry(dialog, width=25, show="*")
        fields["password"].grid(row=row, column=1, padx=5, pady=5)
        
        row += 1
        ttk.Label(dialog, text="Key File:").grid(row=row, column=0, sticky="e", padx=5, pady=5)
        key_frame = ttk.Frame(dialog)
        key_frame.grid(row=row, column=1, padx=5, pady=5)
        fields["key_path"] = ttk.Entry(key_frame, width=18)
        fields["key_path"].pack(side="left")
        ttk.Button(key_frame, text="Browse", command=lambda: self.browse_file_entry(fields["key_path"])).pack(side="left", padx=2)
        
        def save_ssh_connection():
            # Save as SSH-type connection
            config = {
                "connection_type": "ssh",
                "host": fields["host"].get(),
                "port": int(fields["port"].get() or 22),
                "database": "",  # SSH connections don't have database
                "username": fields["user"].get(),
                "password": fields["password"].get() if fields["auth_type"].get() == "password" else "",
                "ssh_key_path": fields["key_path"].get() if fields["auth_type"].get() == "key" else "",
            }
            
            name = fields["name"].get()
            if not name:
                messagebox.showerror("Error", "Connection name is required")
                return
            
            if self.conn_manager.save_connection(name, config):
                dialog.destroy()
                self.load_connections_list()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=row + 1, column=0, columnspan=2, pady=20)
        
        ttk.Button(btn_frame, text="Test SSH", command=lambda: self.test_ssh_from_dialog(fields)).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Save", command=save_ssh_connection).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side="left", padx=5)
        
        # Setup keyboard bindings and focus
        self.setup_dialog_bindings(dialog,
                                 cancel_command=dialog.destroy,
                                 accept_command=save_ssh_connection,
                                 first_field=fields["name"])
    
    def edit_odoo_connection(self):
        """Edit selected Odoo connection"""
        selection = self.odoo_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select an Odoo connection to edit")
            return
        
        # Get connection ID from tree item
        item = self.odoo_tree.item(selection[0])
        conn_id = int(item["tags"][0]) if item["tags"] else None
        
        if not conn_id:
            messagebox.showerror("Error", "Could not get connection ID")
            return
        
        # Get connection details using ID
        conn = self.conn_manager.get_odoo_connection(conn_id)
        if not conn:
            return
        
        original_name = conn["name"]
        original_id = conn_id
        
        # Show edit dialog
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit Connection: {original_name}")
        
        # Set fixed size to match Add dialog
        # Don't set geometry here, will be set after content is built
        
        # Make dialog modal
        dialog.transient(self.root)
        dialog.resizable(False, False)
        
        # Main container with padding
        main_frame = ttk.Frame(dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Connection fields dictionary
        fields = {}
        
        # Load button at top
        ttk.Button(
            main_frame,
            text="Load from odoo.conf",
            command=lambda: self.load_from_odoo_conf(fields),
        ).pack(pady=(0, 15))
        
        # Connection Details Frame
        details_frame = ttk.LabelFrame(main_frame, text="Connection Details", padding="10")
        details_frame.pack(fill=tk.BOTH, expand=False, pady=(0, 10))
        
        # Form fields
        row = 0
        for label, field_name, default_key, width in [
            ("Connection Name:", "name", "name", 30),
            ("Host:", "host", "host", 30),
            ("Port:", "port", "port", 30),
            ("Database:", "database", "database", 30),
            ("Username:", "username", "username", 30),
            ("Password:", "password", "password", 30),
        ]:
            ttk.Label(details_frame, text=label).grid(row=row, column=0, sticky="e", padx=(0, 10), pady=5)
            entry = ttk.Entry(details_frame, width=width)
            if field_name == "password":
                entry.config(show="*")
            # Get value from conn dict, with default
            value = conn.get(default_key, "")
            if field_name == "port":
                value = str(value) if value else "5432"
            entry.insert(0, value)
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            fields[field_name] = entry
            row += 1
        
        # Filestore Path with Browse button
        ttk.Label(details_frame, text="Filestore Path:").grid(row=row, column=0, sticky="e", padx=(0, 10), pady=5)
        path_frame = ttk.Frame(details_frame)
        path_frame.grid(row=row, column=1, sticky="ew", pady=5)
        fields["filestore_path"] = ttk.Entry(path_frame, width=22)
        fields["filestore_path"].insert(0, conn.get("filestore_path", ""))
        fields["filestore_path"].pack(side=tk.LEFT, fill=tk.X, expand=True)
        fields["browse_button"] = ttk.Button(
            path_frame,
            text="Browse",
            command=lambda: self.browse_folder_entry(fields["filestore_path"]),
            width=8
        )
        fields["browse_button"].pack(side=tk.LEFT, padx=(5, 0))
        row += 1
        
        # Odoo Version
        ttk.Label(details_frame, text="Odoo Version:").grid(row=row, column=0, sticky="e", padx=(0, 10), pady=5)
        fields["odoo_version"] = ttk.Combobox(
            details_frame, width=28, values=["18.0", "17.0", "16.0", "15.0", "14.0", "13.0", "12.0"]
        )
        fields["odoo_version"].grid(row=row, column=1, sticky="ew", pady=5)
        fields["odoo_version"].set(conn.get("odoo_version", "17.0"))
        row += 1
        
        # Local Development checkbox
        fields["is_local"] = tk.BooleanVar(value=conn.get("is_local", False))
        ttk.Checkbutton(
            details_frame, text="Local Development Connection", variable=fields["is_local"]
        ).grid(row=row, column=1, sticky="w", pady=5)
        row += 1
        
        # Allow Restore checkbox - handle bad data types
        allow_restore_value = conn.get("allow_restore", False)
        # Convert to boolean if it's not already (handle datetime strings or other bad data)
        if not isinstance(allow_restore_value, bool):
            # Handle integer values (0/1 from database)
            if isinstance(allow_restore_value, int):
                allow_restore_value = bool(allow_restore_value)
            else:
                # Handle strings and other types
                str_val = str(allow_restore_value).lower()
                allow_restore_value = str_val not in ['false', '0', 'none', '', 'null']
        fields["allow_restore"] = tk.BooleanVar(value=allow_restore_value)
        allow_restore_check = ttk.Checkbutton(
            details_frame, 
            text="Allow Restore Operations (⚠️ Be careful with production databases!)", 
            variable=fields["allow_restore"]
        )
        allow_restore_check.grid(row=row, column=1, sticky="w", pady=5)
        
        # Configure column to expand
        details_frame.columnconfigure(1, weight=1)
        
        # SSH Options Frame
        ssh_frame = ttk.LabelFrame(main_frame, text="Remote Server Access", padding="10")
        ssh_frame.pack(fill=tk.BOTH, expand=False, pady=(0, 10))
        
        ssh_conn_id = conn.get("ssh_connection_id")
        fields["use_ssh"] = tk.BooleanVar(value=ssh_conn_id is not None and ssh_conn_id != "")
        ssh_check = ttk.Checkbutton(
            ssh_frame, 
            text="Use SSH connection for remote server access", 
            variable=fields["use_ssh"],
            command=lambda: toggle_ssh_dropdown()
        )
        ssh_check.pack(anchor="w", pady=(0, 5))
        
        # SSH Connection Dropdown
        ssh_select_frame = ttk.Frame(ssh_frame)
        ssh_select_frame.pack(fill=tk.X)
        
        ttk.Label(ssh_select_frame, text="SSH Connection:").pack(side=tk.LEFT, padx=(20, 10))
        
        # Get list of SSH connections
        ssh_connections = []
        ssh_connection_map = {}  # Map names to IDs
        all_connections = self.conn_manager.list_connections()
        for conn_data in all_connections:
            if conn_data['type'] == "ssh":
                ssh_connections.append(conn_data['name'])
                ssh_connection_map[conn_data['name']] = conn_data['id']
        
        fields["ssh_connection"] = ttk.Combobox(
            ssh_select_frame, width=30, values=ssh_connections, state="disabled"
        )
        fields["ssh_connection"].pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Set current SSH connection if it exists
        if conn.get("ssh_connection_id"):
            # Find the name of the SSH connection by ID
            for name, ssh_id in ssh_connection_map.items():
                if ssh_id == conn.get("ssh_connection_id"):
                    fields["ssh_connection"].set(name)
                    fields["ssh_connection"].config(state="readonly")
                    break
            # If we didn't find the SSH connection by ID, it might have been deleted
            # Set the first available SSH connection
            if not fields["ssh_connection"].get() and ssh_connections:
                fields["ssh_connection"].set(ssh_connections[0])
                fields["ssh_connection"].config(state="readonly")
        elif ssh_connections:
            fields["ssh_connection"].set(ssh_connections[0])
        
        def toggle_ssh_dropdown():
            """Enable/disable SSH connection dropdown and browse button based on checkbox"""
            if fields["use_ssh"].get():
                # SSH enabled - enable dropdown, disable browse button
                fields["ssh_connection"].config(state="readonly")
                fields["browse_button"].config(state="disabled")
            else:
                # SSH disabled - disable dropdown, enable browse button
                fields["ssh_connection"].config(state="disabled")
                fields["browse_button"].config(state="normal")
        
        # Set initial state based on whether SSH is being used
        toggle_ssh_dropdown()
        
        # Button frame at bottom
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        def save_connection():
            config = {
                "connection_type": "odoo",
                "host": fields["host"].get(),
                "port": int(fields["port"].get() or 5432),
                "database": fields["database"].get(),
                "username": fields["username"].get(),
                "password": fields["password"].get(),
                "filestore_path": fields["filestore_path"].get(),
                "odoo_version": fields["odoo_version"].get(),
                "is_local": fields["is_local"].get(),
                "allow_restore": fields["allow_restore"].get(),  # Include allow_restore flag
                "use_ssh": fields["use_ssh"].get(),
            }
            
            # If SSH is enabled, find the SSH connection ID
            if fields["use_ssh"].get() and fields["ssh_connection"].get():
                selected_ssh_name = fields["ssh_connection"].get()
                if selected_ssh_name in ssh_connection_map:
                    config["ssh_connection_id"] = ssh_connection_map[selected_ssh_name]
            else:
                config["ssh_connection_id"] = None
            
            new_name = fields["name"].get()
            if not new_name:
                messagebox.showerror("Error", "Connection name is required")
                return
            
            # Update the connection using ID
            if self.conn_manager.update_odoo_connection(original_id, new_name, config):
                dialog.destroy()
                self.load_connections_list()
                self.refresh_connections()
            else:
                messagebox.showerror("Error", "Failed to update connection")
        
        # Center the buttons
        ttk.Button(button_frame, text="Test Connection", 
                  command=lambda: self.test_connection_config(fields)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Save", command=save_connection).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        # Set size and center dialog on parent after it's built
        dialog.update_idletasks()
        # Force proper size to show all content
        width = 550
        height = 680  # Enough for all sections
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (width // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (height // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        
        # Setup keyboard bindings and focus
        self.setup_dialog_bindings(dialog,
                                 cancel_command=dialog.destroy,
                                 accept_command=save_connection,
                                 first_field=fields.get("name"))
    
    def edit_ssh_connection(self):
        """Edit selected SSH connection"""
        selection = self.ssh_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select an SSH connection to edit")
            return
        
        # Get connection ID from tree item
        item = self.ssh_tree.item(selection[0])
        conn_id = int(item["tags"][0]) if item["tags"] else None
        
        if not conn_id:
            messagebox.showerror("Error", "Could not get connection ID")
            return
        
        # Get connection details using ID
        conn = self.conn_manager.get_ssh_connection(conn_id)
        if not conn:
            return
        
        original_name = conn["name"]
        original_id = conn_id
        
        # Show edit dialog
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit SSH Connection: {original_name}")
        dialog.geometry("400x350")
        
        # Center dialog
        self.root.update_idletasks()
        width = 400
        height = 350
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (width // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (height // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        
        dialog.transient(self.root)
        dialog.grab_set()
        
        fields = {}
        row = 0
        
        ttk.Label(dialog, text="Connection Name:").grid(row=row, column=0, sticky="e", padx=5, pady=5)
        fields["name"] = ttk.Entry(dialog, width=25)
        fields["name"].grid(row=row, column=1, padx=5, pady=5)
        fields["name"].insert(0, original_name)
        
        row += 1
        ttk.Label(dialog, text="SSH Host:").grid(row=row, column=0, sticky="e", padx=5, pady=5)
        fields["host"] = ttk.Entry(dialog, width=25)
        fields["host"].grid(row=row, column=1, padx=5, pady=5)
        fields["host"].insert(0, conn.get("host", ""))
        
        row += 1
        ttk.Label(dialog, text="SSH Port:").grid(row=row, column=0, sticky="e", padx=5, pady=5)
        fields["port"] = ttk.Entry(dialog, width=25)
        fields["port"].grid(row=row, column=1, padx=5, pady=5)
        fields["port"].insert(0, str(conn.get("port", 22)))
        
        row += 1
        ttk.Label(dialog, text="SSH User:").grid(row=row, column=0, sticky="e", padx=5, pady=5)
        fields["user"] = ttk.Entry(dialog, width=25)
        fields["user"].grid(row=row, column=1, padx=5, pady=5)
        fields["user"].insert(0, conn.get("username", ""))
        
        row += 1
        ttk.Label(dialog, text="Authentication:").grid(row=row, column=0, sticky="e", padx=5, pady=5)
        auth_frame = ttk.Frame(dialog)
        auth_frame.grid(row=row, column=1, padx=5, pady=5)
        
        # Determine current auth type
        current_auth = "key" if conn.get("ssh_key_path") else "password"
        auth_var = tk.StringVar(value=current_auth)
        ttk.Radiobutton(auth_frame, text="Password", variable=auth_var, value="password").pack(side="left")
        ttk.Radiobutton(auth_frame, text="Key File", variable=auth_var, value="key").pack(side="left")
        fields["auth_type"] = auth_var
        
        row += 1
        ttk.Label(dialog, text="Password:").grid(row=row, column=0, sticky="e", padx=5, pady=5)
        fields["password"] = ttk.Entry(dialog, width=25, show="*")
        fields["password"].grid(row=row, column=1, padx=5, pady=5)
        if conn.get("password"):
            fields["password"].insert(0, conn.get("password", ""))
        
        row += 1
        ttk.Label(dialog, text="Key File:").grid(row=row, column=0, sticky="e", padx=5, pady=5)
        key_frame = ttk.Frame(dialog)
        key_frame.grid(row=row, column=1, padx=5, pady=5)
        fields["key_path"] = ttk.Entry(key_frame, width=18)
        fields["key_path"].pack(side="left")
        fields["key_path"].insert(0, conn.get("ssh_key_path", ""))
        ttk.Button(key_frame, text="Browse", command=lambda: self.browse_file_entry(fields["key_path"])).pack(side="left", padx=2)
        
        def save_ssh_connection():
            # Save updated SSH connection
            config = {
                "connection_type": "ssh",
                "host": fields["host"].get(),
                "port": int(fields["port"].get() or 22),
                "database": "",  # SSH connections don't have database
                "username": fields["user"].get(),
                "password": fields["password"].get() if fields["auth_type"].get() == "password" else "",
                "ssh_key_path": fields["key_path"].get() if fields["auth_type"].get() == "key" else "",
            }
            
            new_name = fields["name"].get()
            if not new_name:
                messagebox.showerror("Error", "Connection name is required")
                return
            
            # Update the connection using ID
            if self.conn_manager.update_ssh_connection(original_id, new_name, config):
                dialog.destroy()
                self.load_connections_list()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=row + 1, column=0, columnspan=2, pady=20)
        
        ttk.Button(btn_frame, text="Test SSH", command=lambda: self.test_ssh_from_dialog(fields)).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Save", command=save_ssh_connection).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side="left", padx=5)
        
        # Setup keyboard bindings and focus
        self.setup_dialog_bindings(dialog,
                                 cancel_command=dialog.destroy,
                                 accept_command=save_ssh_connection,
                                 first_field=fields["name"])
    
    def delete_odoo_connection(self):
        """Delete selected Odoo connection"""
        selection = self.odoo_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select an Odoo connection to delete")
            return
        
        item = self.odoo_tree.item(selection[0])
        conn_name = item["text"]
        
        if messagebox.askyesno("Confirm", f"Delete Odoo connection '{conn_name}'?"):
            if self.conn_manager.delete_connection(conn_name):
                self.load_connections_list()
                self.refresh_connections()
    
    def delete_ssh_connection(self):
        """Delete selected SSH connection"""
        selection = self.ssh_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select an SSH connection to delete")
            return
        
        item = self.ssh_tree.item(selection[0])
        conn_name = item["text"]
        
        if messagebox.askyesno("Confirm", f"Delete SSH connection '{conn_name}'?"):
            if self.conn_manager.delete_connection(conn_name):
                self.load_connections_list()
    
    def test_selected_connection(self, conn_type):
        """Test the selected connection"""
        if conn_type == "odoo":
            selection = self.odoo_tree.selection()
            if not selection:
                messagebox.showwarning("Warning", "Please select an Odoo connection to test")
                return
            
            item = self.odoo_tree.item(selection[0])
            conn_id = int(item["tags"][0]) if item["tags"] else None
            conn_name = item["text"]
            
            if not conn_id:
                messagebox.showerror("Error", "Could not get connection ID")
                return
            
            # Get connection and test it using ID
            conn = self.conn_manager.get_odoo_connection(conn_id)
            if conn:
                tool = OdooBench(conn_manager=self.conn_manager)
                config = {
                    "db_host": conn.get("host"),
                    "db_port": conn.get("port"),
                    "db_user": conn.get("username"),
                    "db_password": conn.get("password"),
                    "db_name": conn.get("database"),
                }
                success, msg = tool.test_connection(config)
                
                if success:
                    messagebox.showinfo("Success", f"Odoo database connection '{conn_name}' successful!")
                else:
                    messagebox.showerror("Error", f"Odoo connection '{conn_name}' failed: {msg}")
        
        elif conn_type == "ssh":
            selection = self.ssh_tree.selection()
            if not selection:
                messagebox.showwarning("Warning", "Please select an SSH connection to test")
                return
            
            item = self.ssh_tree.item(selection[0])
            conn_id = int(item["tags"][0]) if item["tags"] else None
            conn_name = item["text"]
            
            if not conn_id:
                messagebox.showerror("Error", "Could not get connection ID")
                return
            
            # Get connection details using ID
            conn = self.conn_manager.get_ssh_connection(conn_id)
            if not conn:
                messagebox.showerror("Error", f"Could not load connection: {conn_name}")
                return
            
            try:
                # Show progress (safely try to set cursor)
                try:
                    self.root.config(cursor="watch")
                    self.root.update()
                except:
                    pass  # Ignore cursor errors
                
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                connect_kwargs = {
                    "hostname": conn.get("host"),
                    "port": conn.get("port", 22),
                    "username": conn.get("username"),
                    "timeout": 10,  # Add timeout
                    "banner_timeout": 10,
                    "auth_timeout": 10,
                }
                
                # Use password or key authentication
                if conn.get("ssh_key_path"):
                    if os.path.exists(conn.get("ssh_key_path")):
                        connect_kwargs["key_filename"] = conn.get("ssh_key_path")
                    else:
                        messagebox.showerror("Error", f"SSH key file not found: {conn.get('ssh_key_path')}")
                        return
                elif conn.get("password"):
                    connect_kwargs["password"] = conn.get("password")
                else:
                    messagebox.showerror("Error", "No authentication method available (no password or key)")
                    return
                
                # Try to connect with timeout
                ssh.connect(**connect_kwargs)
                
                # Execute a simple command to verify connection with timeout
                stdin, stdout, stderr = ssh.exec_command("echo 'SSH connection test successful'", timeout=5)
                output = stdout.read().decode().strip()
                error = stderr.read().decode().strip()
                
                ssh.close()
                
                if "SSH connection test successful" in output:
                    messagebox.showinfo("Success", f"SSH connection '{conn_name}' successful!")
                elif error:
                    messagebox.showwarning("Warning", f"SSH connected but command failed:\n{error}")
                else:
                    messagebox.showwarning("Warning", f"SSH connection established but test command failed")
                    
            except paramiko.AuthenticationException as e:
                messagebox.showerror("Authentication Failed", f"SSH authentication failed for '{conn_name}':\n{str(e)}")
            except paramiko.SSHException as e:
                messagebox.showerror("SSH Error", f"SSH connection error for '{conn_name}':\n{str(e)}")
            except socket.timeout:
                messagebox.showerror("Timeout", f"SSH connection '{conn_name}' timed out after 10 seconds")
            except Exception as e:
                messagebox.showerror("Error", f"SSH connection '{conn_name}' failed:\n{str(e)}")
            finally:
                try:
                    self.root.config(cursor="")
                except:
                    pass  # Ignore cursor errors
    
    def test_ssh_from_dialog(self, fields):
        """Test SSH connection from dialog fields"""
        try:
            # Show progress (safely try to set cursor)
            try:
                self.root.config(cursor="watch")
                self.root.update()
            except:
                pass  # Ignore cursor errors
            
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            connect_kwargs = {
                "hostname": fields["host"].get(),
                "port": int(fields["port"].get() or 22),
                "username": fields["user"].get(),
                "timeout": 10,  # Add 10 second timeout
                "banner_timeout": 10,  # Add banner timeout
                "auth_timeout": 10,  # Add auth timeout
            }
            
            if not connect_kwargs["hostname"]:
                messagebox.showerror("Error", "SSH host is required")
                return
            
            if not connect_kwargs["username"]:
                messagebox.showerror("Error", "SSH username is required")
                return
            
            if fields["auth_type"].get() == "password":
                password = fields["password"].get()
                if not password:
                    messagebox.showerror("Error", "Password is required for password authentication")
                    return
                connect_kwargs["password"] = password
            else:
                key_path = fields["key_path"].get()
                if not key_path:
                    messagebox.showerror("Error", "Key file path is required for key authentication")
                    return
                if not os.path.exists(key_path):
                    messagebox.showerror("Error", f"Key file not found: {key_path}")
                    return
                connect_kwargs["key_filename"] = key_path
            
            # Try to connect with timeout
            ssh.connect(**connect_kwargs)
            
            # Execute test command with timeout
            stdin, stdout, stderr = ssh.exec_command("echo 'SSH test OK'", timeout=5)
            output = stdout.read().decode().strip()
            error = stderr.read().decode().strip()
            
            ssh.close()
            
            if "SSH test OK" in output:
                messagebox.showinfo("Success", "SSH connection successful!")
            elif error:
                messagebox.showwarning("Warning", f"SSH connected but command failed:\n{error}")
            else:
                messagebox.showwarning("Warning", "SSH connected but no response from test command")
            
        except paramiko.AuthenticationException as e:
            messagebox.showerror("Authentication Failed", f"SSH authentication failed:\n{str(e)}")
        except paramiko.SSHException as e:
            messagebox.showerror("SSH Error", f"SSH connection error:\n{str(e)}")
        except socket.timeout:
            messagebox.showerror("Timeout", "SSH connection timed out after 10 seconds")
        except Exception as e:
            messagebox.showerror("Error", f"SSH connection failed:\n{str(e)}")
        finally:
            try:
                self.root.config(cursor="")
            except:
                pass  # Ignore cursor errors
    
    def refresh_connections(self):
        """Refresh connection dropdowns"""
        connections = self.conn_manager.list_connections()
        # Filter only Odoo connections for backup/restore
        # Store mapping of names to IDs
        self.odoo_conn_map = {}
        source_names = []  # All Odoo connections can be sources
        dest_names = []    # Only connections with allow_restore=True can be destinations
        
        for conn in connections:
            if conn['type'] == 'odoo':
                source_names.append(conn['name'])
                self.odoo_conn_map[conn['name']] = conn['id']
                
                # Only add to destination list if restore is allowed
                if conn.get('allow_restore', False):
                    dest_names.append(conn['name'])

        self.source_combo["values"] = source_names
        self.dest_combo["values"] = dest_names

    def load_connection(self, target):
        """Load selected connection details"""
        if target == "source":
            conn_name = self.source_conn.get()
            info_label = self.source_info_label
        else:
            conn_name = self.dest_conn.get()
            info_label = self.dest_info_label

        if not conn_name:
            return

        # Get Odoo connection by ID
        if hasattr(self, 'odoo_conn_map') and conn_name in self.odoo_conn_map:
            conn_id = self.odoo_conn_map[conn_name]
            conn = self.conn_manager.get_odoo_connection(conn_id)
            if conn:
                info = f"{conn['host']}:{conn['port']}/{conn['database']}"
                if conn.get("filestore_path"):
                    info += f"\nFilestore: {conn['filestore_path']}"
                info_label.config(text=info)


    def browse_backup_dir(self):
        """Browse for backup directory"""
        folder = filedialog.askdirectory()
        if folder:
            self.backup_dir_path.set(folder)
    
    def on_source_selected(self):
        """Handle source connection selection"""
        # Load connection details
        self.load_connection("source")
        
        # Update window size after loading connection details
        self.update_window_size()
        
        # If in backup-only mode, set default backup filename
        if self.operation_mode.get() == "backup_only":
            conn_name = self.source_conn.get()
            if conn_name:
                # Generate timestamp
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                # Use configured backup directory
                default_dir = self.backup_directory
                
                # Create default filename
                default_filename = os.path.join(default_dir, f"backup_{conn_name}_{timestamp}.tar.gz")
                
                # Set the backup file path
                self.backup_file_var.set(default_filename)
    
    def update_window_size(self):
        """Force window to recalculate its natural size after showing/hiding elements"""
        self.root.update_idletasks()  # Force geometry calculation
        # Don't set geometry - let window auto-size to content
        
    def update_operation_ui(self):
        """Update UI based on selected operation mode"""
        mode = self.operation_mode.get()
        
        # Hide all frames first
        self.backup_file_frame.pack_forget()
        self.restore_file_frame.pack_forget()
        self.source_frame.pack_forget()
        self.dest_frame.pack_forget()
        
        # Get the parent and find where to insert (after Operation Mode frame)
        # We need to re-pack in the correct order
        
        if mode == "backup_restore":
            # Show both source and destination
            self.source_frame.pack(fill="x", pady=5, after=self.mode_frame)
            self.dest_frame.pack(fill="x", pady=5, after=self.source_frame)
            self.execute_btn.config(text="Execute Backup & Restore")
        elif mode == "backup_only":
            # Show only source
            self.source_frame.pack(fill="x", pady=5, after=self.mode_frame)
            # Show backup file selector
            self.backup_file_frame.pack(side="left")
            self.execute_btn.config(text="Execute Backup")
            
            # If a source is already selected, set default filename
            conn_name = self.source_conn.get()
            if conn_name:
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                default_dir = self.backup_directory
                default_filename = os.path.join(default_dir, f"backup_{conn_name}_{timestamp}.tar.gz")
                self.backup_file_var.set(default_filename)
        elif mode == "restore_only":
            # Show only destination  
            self.dest_frame.pack(fill="x", pady=5, after=self.mode_frame)
            # Show restore file selector
            self.restore_file_frame.pack(side="left")
            self.execute_btn.config(text="Execute Restore")
            # Refresh available restore files for the selected destination
            self.refresh_restore_files()
            
        # Update window size after UI changes
        self.update_window_size()
    
    def on_dest_selected(self):
        """Handle destination connection selection"""
        # Load the connection details
        self.load_connection("dest")
        
        # Update window size after loading connection details
        self.update_window_size()
        
        # If in restore_only mode, refresh the restore files dropdown
        if self.operation_mode.get() == "restore_only":
            self.refresh_restore_files()
    
    def refresh_restore_files(self):
        """Refresh the list of all available backup files for restore dropdown"""
        # Get list of ALL backup files (full paths)
        backup_files = self.get_all_backup_files()
        
        # Show only filenames in the dropdown
        filenames = [os.path.basename(f) for f in backup_files]
        self.restore_file_combo['values'] = filenames
        
        # Store the mapping of filename to full path
        self.restore_file_mapping = {os.path.basename(f): f for f in backup_files}
        
        # If there are files and nothing is selected, select the most recent
        if filenames and not self.restore_file_var.get():
            self.restore_file_var.set(filenames[0])
    
    def get_all_backup_files(self):
        """Get list of all backup files in the backup directory"""
        backup_files = []
        
        # Look for all backup files in the backup directory
        if os.path.exists(self.backup_directory):
            for filename in os.listdir(self.backup_directory):
                # Check for all .tar.gz, .tgz and .zip files
                if filename.endswith('.tar.gz') or filename.endswith('.tgz') or filename.endswith('.zip'):
                    full_path = os.path.join(self.backup_directory, filename)
                    if os.path.isfile(full_path):
                        backup_files.append(full_path)
        
        # Sort files by modification time (newest first)
        backup_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        return backup_files
    
    def browse_backup_file(self):
        """Browse for backup zip file location"""
        filename = filedialog.asksaveasfilename(
            initialdir=self.backup_directory,
            defaultextension=".tar.gz",
            filetypes=[("TAR.GZ files", "*.tar.gz"), ("ZIP files", "*.zip"), ("All files", "*.*")],
            title="Save backup as..."
        )
        if filename:
            self.backup_file_var.set(filename)
    
    def browse_restore_file(self):
        """Browse for restore zip file"""
        filename = filedialog.askopenfilename(
            initialdir=self.backup_directory,
            filetypes=[("TAR.GZ files", "*.tar.gz"), ("ZIP files", "*.zip"), ("All files", "*.*")],
            title="Select backup file to restore..."
        )
        if filename:
            # If the file is in the backup directory, store just the filename
            if os.path.dirname(filename) == self.backup_directory:
                basename = os.path.basename(filename)
                self.restore_file_var.set(basename)
                # Add to mapping
                self.restore_file_mapping[basename] = filename
            else:
                # Store full path for files outside backup directory
                self.restore_file_var.set(filename)

    def test_connection(self, target):
        """Test selected connection"""
        if target == "source":
            conn_name = self.source_conn.get()
        else:
            conn_name = self.dest_conn.get()

        if not conn_name:
            messagebox.showwarning("Warning", f"Please select a {target} connection")
            return

        # Get connection by ID
        if not hasattr(self, 'odoo_conn_map') or conn_name not in self.odoo_conn_map:
            messagebox.showerror("Error", f"Connection '{conn_name}' not found")
            return
        
        conn_id = self.odoo_conn_map[conn_name]
        conn = self.conn_manager.get_odoo_connection(conn_id)
        if not conn:
            return

        config = {
            "db_host": conn["host"],
            "db_port": conn["port"],
            "db_user": conn["username"],
            "db_password": conn["password"],
            "db_name": conn["database"],
        }

        tool = OdooBench(conn_manager=self.conn_manager)
        success, msg = tool.test_connection(config)

        if success:
            messagebox.showinfo("Success", f"{target.title()} connection successful!")
            self.log_message(f"{target.title()} connection test successful", "success")
        else:
            messagebox.showerror("Error", f"{target.title()} connection failed: {msg}")
            self.log_message(f"{target.title()} connection test failed: {msg}", "error")

    def log_message(self, message, level="info"):
        """Add message to log"""
        self.log_text.insert(
            tk.END, f"{datetime.now().strftime('%H:%M:%S')} - {message}\n", level
        )
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def clear_log(self):
        """Clear log text"""
        self.log_text.delete(1.0, tk.END)

    def update_progress(self, value, message=""):
        """Update progress bar"""
        self.progress_bar["value"] = value
        if message:
            self.progress_label.config(text=message)
        self.root.update_idletasks()

    def execute_operation(self):
        """Execute the selected operation (backup, restore, or both)"""
        mode = self.operation_mode.get()
        
        if mode == "backup_restore":
            self.execute_backup_restore()
        elif mode == "backup_only":
            self.execute_backup_only()
        elif mode == "restore_only":
            self.execute_restore_only()
    
    def execute_backup_only(self):
        """Execute backup only to zip file"""
        source_name = self.source_conn.get()
        backup_file = self.backup_file_var.get()
        
        if not source_name:
            messagebox.showerror("Error", "Please select a source connection")
            return
        
        if not backup_file:
            messagebox.showerror("Error", "Please specify where to save the backup")
            return
        
        # Get source connection by ID
        if not hasattr(self, 'odoo_conn_map') or source_name not in self.odoo_conn_map:
            messagebox.showerror("Error", "Source connection not found")
            return
        
        source_conn_id = self.odoo_conn_map[source_name]
        source_conn = self.conn_manager.get_odoo_connection(source_conn_id)
        
        if not source_conn:
            messagebox.showerror("Error", "Failed to load source connection details")
            return
        
        # Prepare source configuration
        source_config = {
            "db_host": source_conn["host"],
            "db_port": source_conn["port"],
            "db_user": source_conn["username"],
            "db_password": source_conn["password"],
            "db_name": source_conn["database"],
            "filestore_path": source_conn["filestore_path"],
            "odoo_version": source_conn.get("odoo_version", ""),
            "db_only": self.db_only.get(),
            "filestore_only": self.filestore_only.get(),
            "use_ssh": source_conn.get("use_ssh", False),
            "ssh_connection_id": source_conn.get("ssh_connection_id"),
        }
        
        # Execute backup in thread
        def run_backup():
            try:
                self.log_message("Starting backup operation...", "info")
                # Create tool with callbacks
                tool = OdooBench(
                    progress_callback=lambda val, msg: self.update_progress(val, msg),
                    log_callback=lambda msg, level: self.log_message(msg, level),
                    conn_manager=self.conn_manager
                )
                
                # Create backup
                self.log_message(f"Creating backup of {source_conn['database']}...", "info")
                backup_path = tool.backup(source_config)
                
                if backup_path:
                    # Move/rename to the specified file
                    import shutil
                    shutil.move(backup_path, backup_file)
                    self.log_message(f"Backup saved to: {backup_file}", "success")
                    self.refresh_backup_files()  # Refresh the file list
                    messagebox.showinfo("Success", f"Backup completed successfully!\nSaved to: {backup_file}")
                else:
                    self.log_message("Backup failed", "error")
                    messagebox.showerror("Error", "Backup operation failed")
                    
            except Exception as e:
                error_msg = str(e)
                self.log_message(f"Error: {error_msg}", "error")
                messagebox.showerror("Error", f"Backup failed:\n{error_msg}")
            finally:
                self.progress_bar.stop()
                self.execute_btn.config(state="normal")
        
        # Start backup in thread
        self.execute_btn.config(state="disabled")
        self.progress_bar.start()
        threading.Thread(target=run_backup, daemon=True).start()
    
    def execute_restore_only(self):
        """Execute restore only from zip file"""
        dest_name = self.dest_conn.get()
        restore_file = self.restore_file_var.get()
        
        if not dest_name:
            messagebox.showerror("Error", "Please select a destination connection")
            return
        
        if not restore_file:
            messagebox.showerror("Error", "Please select a backup file to restore")
            return
        
        # Get the full path from the mapping if it's just a filename
        if restore_file in self.restore_file_mapping:
            restore_file = self.restore_file_mapping[restore_file]
        elif not os.path.isabs(restore_file):
            # If it's not in mapping and not absolute, prepend backup directory
            restore_file = os.path.join(self.backup_directory, restore_file)
        
        if not os.path.exists(restore_file):
            messagebox.showerror("Error", f"Backup file not found: {restore_file}")
            return
        
        # Get destination connection by ID
        if not hasattr(self, 'odoo_conn_map') or dest_name not in self.odoo_conn_map:
            messagebox.showerror("Error", "Destination connection not found")
            return
        
        dest_conn_id = self.odoo_conn_map[dest_name]
        dest_conn = self.conn_manager.get_odoo_connection(dest_conn_id)
        
        if not dest_conn:
            messagebox.showerror("Error", "Failed to load destination connection details")
            return
        
        # Check if restore is allowed for this connection
        if not dest_conn.get('allow_restore', False):
            messagebox.showerror(
                "Restore Protected", 
                f"Restore operations are not allowed for connection '{dest_name}'.\n\n"
                f"This is a production database that is protected from restore operations.\n"
                f"To enable restore, update the connection settings and explicitly allow restore."
            )
            return
        
        # Prepare destination configuration
        dest_config = {
            "db_host": dest_conn["host"],
            "db_port": dest_conn["port"],
            "db_user": dest_conn["username"],
            "db_password": dest_conn["password"],
            "db_name": dest_conn["database"],
            "filestore_path": dest_conn["filestore_path"],
            "odoo_version": dest_conn.get("odoo_version", ""),
            "db_only": self.db_only.get(),
            "filestore_only": self.filestore_only.get(),
            "neutralize": self.neutralize.get(),
            "use_ssh": dest_conn.get("use_ssh", False),
            "ssh_connection_id": dest_conn.get("ssh_connection_id"),
        }
        
        # Create custom confirmation dialog
        confirm_dialog = tk.Toplevel(self.root)
        confirm_dialog.title("Confirm Restore")
        confirm_dialog.transient(self.root)
        confirm_dialog.grab_set()
        
        # Set dialog size - increased height to fit all content
        window_width = 520
        window_height = 520  # Increased to fit all neutralization warnings and buttons
        confirm_dialog.geometry(f"{window_width}x{window_height}")
        
        # Center on parent window
        confirm_dialog.update_idletasks()
        parent_x = self.root.winfo_x()
        parent_y = self.root.winfo_y()
        parent_width = self.root.winfo_width()
        parent_height = self.root.winfo_height()
        
        # Calculate center position relative to parent
        x = parent_x + (parent_width - window_width) // 2
        y = parent_y + (parent_height - window_height) // 2
        
        # Ensure dialog stays on screen
        x = max(10, x)
        y = max(10, y)
        
        confirm_dialog.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # Create the message
        msg_frame = ttk.Frame(confirm_dialog, padding="20")
        msg_frame.pack(fill="both", expand=True)
        
        ttk.Label(msg_frame, text="Are you sure you want to restore?", 
                 font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(0, 10))
        
        ttk.Label(msg_frame, text=f"Backup file: {os.path.basename(restore_file)}").pack(anchor="w", pady=2)
        ttk.Label(msg_frame, text=f"Destination: {dest_name}").pack(anchor="w", pady=2)
        
        ttk.Separator(msg_frame, orient="horizontal").pack(fill="x", pady=10)
        
        ttk.Label(msg_frame, text="⚠️ WARNING - This will PERMANENTLY DELETE:", 
                 font=("TkDefaultFont", 10, "bold"), foreground="#CC0000").pack(anchor="w", pady=(0, 5))
        
        # Only show database deletion warning if not filestore_only
        if not dest_config.get('filestore_only', False):
            ttk.Label(msg_frame, text=f"• Database: {dest_config['db_name']}", 
                     foreground="#CC0000").pack(anchor="w", padx=(20, 0), pady=2)
        
        # Only show filestore deletion warning if not db_only
        if not dest_config.get('db_only', False) and dest_config.get('filestore_path'):
            ttk.Label(msg_frame, text=f"• Filestore at: {dest_config['filestore_path']}/filestore/{dest_config['db_name']}", 
                     foreground="#CC0000").pack(anchor="w", padx=(20, 0), pady=2)
        
        ttk.Label(msg_frame, text="", font=("TkDefaultFont", 1)).pack()  # Small spacer
        ttk.Label(msg_frame, text="⚠️ BACKUP YOUR DATA FIRST IF YOU NEED IT!", 
                 font=("TkDefaultFont", 9, "bold"), foreground="#CC0000").pack(anchor="w", pady=2)
        
        # Show neutralization warning if enabled
        if self.neutralize.get():
            ttk.Label(msg_frame, text="").pack(pady=5)  # Spacer
            ttk.Label(msg_frame, text="⚠️ NEUTRALIZATION ENABLED:", 
                     font=("TkDefaultFont", 10, "bold"), foreground="#CC0000").pack(anchor="w", pady=2)
            ttk.Label(msg_frame, text="• All email servers will be disabled", foreground="#CC0000").pack(anchor="w", padx=(20, 0), pady=2)
            ttk.Label(msg_frame, text="• Email configurations will be removed", foreground="#CC0000").pack(anchor="w", padx=(20, 0), pady=2)
            ttk.Label(msg_frame, text="• All email queues will be cleared", foreground="#CC0000").pack(anchor="w", padx=(20, 0), pady=2)
            ttk.Label(msg_frame, text="• All scheduled actions (crons) will be disabled", foreground="#CC0000").pack(anchor="w", padx=(20, 0), pady=2)
            ttk.Label(msg_frame, text="• Company name will be prefixed with [TEST]", foreground="#CC0000").pack(anchor="w", padx=(20, 0), pady=2)
        
        # Result variable
        result = {"confirmed": False}
        
        def on_yes():
            result["confirmed"] = True
            confirm_dialog.destroy()
        
        def on_no():
            confirm_dialog.destroy()
        
        # Button frame
        btn_frame = ttk.Frame(confirm_dialog)
        btn_frame.pack(side="bottom", pady=20)
        
        # Yes button (with danger styling)
        yes_btn = ttk.Button(btn_frame, text="Yes", command=on_yes, width=12)
        yes_btn.pack(side="left", padx=10)
        
        # No button (default)
        no_btn = ttk.Button(btn_frame, text="No", command=on_no, width=12)
        no_btn.pack(side="left", padx=10)
        
        # Setup keyboard bindings (No is the safe default for Enter)
        self.setup_dialog_bindings(confirm_dialog,
                                 cancel_command=on_no,
                                 accept_command=on_no,  # Safe default
                                 first_field=no_btn)  # Focus on No button
        
        # Wait for dialog to close
        self.root.wait_window(confirm_dialog)
        
        if not result["confirmed"]:
            return
        
        # Execute restore in thread
        def run_restore():
            try:
                self.log_message("Starting restore operation...", "info")
                # Create tool with callbacks
                tool = OdooBench(
                    progress_callback=lambda val, msg: self.update_progress(val, msg),
                    log_callback=lambda msg, level: self.log_message(msg, level),
                    conn_manager=self.conn_manager
                )
                
                # Restore from backup file
                self.log_message(f"Restoring from {restore_file} to {dest_conn['database']}...", "info")
                success = tool.restore(dest_config, restore_file)
                
                if success:
                    self.log_message("Restore completed successfully!", "success")
                    messagebox.showinfo("Success", "Restore completed successfully!")
                else:
                    self.log_message("Restore failed", "error")
                    messagebox.showerror("Error", "Restore operation failed")
                    
            except Exception as e:
                error_msg = str(e)
                self.log_message(f"Error: {error_msg}", "error")
                messagebox.showerror("Error", f"Restore failed:\n{error_msg}")
            finally:
                self.progress_bar.stop()
                self.execute_btn.config(state="normal")
        
        # Start restore in thread
        self.execute_btn.config(state="disabled")
        self.progress_bar.start()
        threading.Thread(target=run_restore, daemon=True).start()

    def execute_backup_restore(self):
        """Execute backup and restore operation"""
        # Get source and destination connections
        source_name = self.source_conn.get()
        dest_name = self.dest_conn.get()

        if not source_name or not dest_name:
            messagebox.showerror(
                "Error", "Please select both source and destination connections"
            )
            return

        # Get connections by ID
        if not hasattr(self, 'odoo_conn_map'):
            messagebox.showerror("Error", "No connections available")
            return
        
        if source_name not in self.odoo_conn_map or dest_name not in self.odoo_conn_map:
            messagebox.showerror("Error", "Failed to find connection details")
            return
        
        source_conn_id = self.odoo_conn_map[source_name]
        dest_conn_id = self.odoo_conn_map[dest_name]
        
        source_conn = self.conn_manager.get_odoo_connection(source_conn_id)
        dest_conn = self.conn_manager.get_odoo_connection(dest_conn_id)

        if not source_conn or not dest_conn:
            messagebox.showerror("Error", "Failed to load connection details")
            return
        
        # Check if restore is allowed for destination connection
        if not dest_conn.get('allow_restore', False):
            messagebox.showerror(
                "Restore Protected", 
                f"Restore operations are not allowed for connection '{dest_name}'.\n\n"
                f"This is a production database that is protected from restore operations.\n"
                f"To enable restore, update the connection settings and explicitly allow restore."
            )
            return

        # Prepare configurations
        source_config = {
            "db_host": source_conn["host"],
            "db_port": source_conn["port"],
            "db_user": source_conn["username"],
            "db_password": source_conn["password"],
            "db_name": source_conn["database"],
            "filestore_path": source_conn["filestore_path"],
            "odoo_version": source_conn.get("odoo_version", ""),
            "db_only": self.db_only.get(),
            "filestore_only": self.filestore_only.get(),
            "save_backup": True,  # Always save backup in backup & restore mode
            "backup_dir": self.backup_dir_path.get(),  # Always use backup directory
            "use_ssh": source_conn.get("use_ssh", False),
            "ssh_connection_id": source_conn.get("ssh_connection_id"),
        }

        dest_config = {
            "db_host": dest_conn["host"],
            "db_port": dest_conn["port"],
            "db_user": dest_conn["username"],
            "db_password": dest_conn["password"],
            "db_name": dest_conn["database"],
            "filestore_path": dest_conn["filestore_path"],
            "db_only": self.db_only.get(),
            "filestore_only": self.filestore_only.get(),
            "use_ssh": dest_conn.get("use_ssh", False),
            "ssh_connection_id": dest_conn.get("ssh_connection_id"),
        }

        # Confirm operation
        msg = f"This will:\n"
        msg += f"1. Backup from: {source_conn['host']}/{source_conn['database']}\n"
        msg += f"2. Restore to: {dest_conn['host']}/{dest_conn['database']}\n"
        msg += "\n⚠️ Warning: This will OVERWRITE the destination database!"

        if not messagebox.askyesno("Confirm Operation", msg):
            return

        # Disable execute button
        self.execute_btn.config(state="disabled")
        self.clear_log()

        # Run in thread
        thread = threading.Thread(
            target=self.run_backup_restore, args=(source_config, dest_config)
        )
        thread.daemon = True
        thread.start()

    def run_backup_restore(self, source_config, dest_config):
        """Run backup and restore in thread"""
        try:
            tool = OdooBench(
                progress_callback=lambda v, m: self.root.after(
                    0, self.update_progress, v, m
                ),
                log_callback=lambda m, l: self.root.after(0, self.log_message, m, l),
                conn_manager=self.conn_manager
            )

            # Check dependencies
            tool.check_dependencies()

            # Execute backup and restore
            tool.backup_and_restore(source_config, dest_config)

            self.root.after(
                0,
                lambda: messagebox.showinfo(
                    "Success",
                    f"✅ Backup and restore completed successfully!\n\n"
                    f"Source: {source_config['db_name']}\n"
                    f"Destination: {dest_config['db_name']}",
                ),
            )

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.root.after(
                0, lambda: self.log_message(f"Operation failed: {str(e)}", "error")
            )

        finally:
            self.root.after(0, lambda: self.execute_btn.config(state="normal"))


