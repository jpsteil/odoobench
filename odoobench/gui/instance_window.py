"""
Main Instance Manager Window for OdooBench
New layout with left pane for connections and tabbed interface per connection
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont
import threading
import os
import re
from datetime import datetime
from typing import Optional, Dict, Any, List

from ..db.odoo_connection_manager import OdooInstanceManager
from ..core.executor import create_executor, ConnectionExecutor
from ..core.odoo_config_parser import OdooConfigParser
from ..core.backup_restore import OdooBench
from ..version import __version__


class InstanceWindow:
    """Main window with left pane for connections and tabbed content"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"OdooBench v{__version__}")
        self.root.minsize(900, 600)

        # Initialize managers
        self.instance_manager = OdooInstanceManager()

        # Track open connections
        self.open_connections: Dict[int, Dict[str, Any]] = {}
        # Maps instance_id -> {'executor': executor, 'tab_id': tab_widget, 'feature_notebook': notebook}

        # Load settings
        self.dark_mode_var = tk.BooleanVar(
            value=self.instance_manager.get_setting("dark_mode", "0") == "1"
        )
        self.font_size = int(self.instance_manager.get_setting("font_size", "10"))
        self.backup_directory = self.instance_manager.get_setting(
            "backup_directory",
            os.path.expanduser("~/Documents/OdooBackups")
        )

        # Ensure backup directory exists
        if not os.path.exists(self.backup_directory):
            try:
                os.makedirs(self.backup_directory, exist_ok=True)
            except Exception:
                self.backup_directory = os.path.expanduser("~")

        # Build UI
        self._create_menu()
        self._create_main_layout()
        self._apply_theme()
        self._apply_font_size()

        # Restore window geometry and layout
        self._restore_geometry()
        self.root.after(100, self._restore_layout)  # Delay to let widgets render

        # Load connections
        self._refresh_connection_tree()

        # Restore previously open connections (delayed to let tree render)
        self.root.after(200, self._restore_open_connections)

        # Bind close event to save state
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Bind Configure event to save geometry/layout when window is resized/moved
        self._geometry_save_pending = False
        self.root.bind('<Configure>', self._on_configure)

        # Start periodic autosave (every 30 seconds)
        self._start_autosave()

    def _create_menu(self):
        """Create the menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Connection...", command=self._new_connection)
        file_menu.add_separator()
        file_menu.add_command(label="Export Connections...", command=self._export_connections)
        file_menu.add_command(label="Import Connections...", command=self._import_connections)
        file_menu.add_separator()
        file_menu.add_command(label="Settings...", command=self._show_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._show_about)

    def _create_main_layout(self):
        """Create the main paned window layout"""
        # Main horizontal paned window
        self.main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left pane - Connection tree
        self._create_left_pane()

        # Right pane - Connection tabs
        self._create_right_pane()

    def _create_left_pane(self):
        """Create the left pane with connection tree"""
        left_frame = ttk.Frame(self.main_paned, width=250)
        self.main_paned.add(left_frame, weight=0)

        # Header
        header_frame = ttk.Frame(left_frame)
        header_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(header_frame, text="Connections", font=('TkDefaultFont', 10, 'bold')).pack(side=tk.LEFT)

        # Buttons frame
        btn_frame = ttk.Frame(header_frame)
        btn_frame.pack(side=tk.RIGHT)

        ttk.Button(btn_frame, text="+", width=3, command=self._new_connection).pack(side=tk.LEFT, padx=2)

        # Treeview for connections
        tree_frame = ttk.Frame(left_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.conn_tree = ttk.Treeview(tree_frame, selectmode='browse', show='tree')
        self.conn_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.conn_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.conn_tree.configure(yscrollcommand=scrollbar.set)

        # Bind events
        self.conn_tree.bind('<Double-1>', self._on_connection_double_click)
        self.conn_tree.bind('<Return>', self._on_connection_double_click)
        self.conn_tree.bind('<Button-3>', self._on_connection_right_click)

        # Context menu
        self.conn_context_menu = tk.Menu(self.root, tearoff=0)
        self.conn_context_menu.add_command(label="Connect", command=self._connect_selected)
        self.conn_context_menu.add_command(label="Edit...", command=self._edit_selected)
        self.conn_context_menu.add_separator()
        self.conn_context_menu.add_command(label="Delete", command=self._delete_selected)

    def _create_right_pane(self):
        """Create the right pane with connection tabs"""
        right_frame = ttk.Frame(self.main_paned)
        self.main_paned.add(right_frame, weight=1)

        # Notebook for open connections
        self.connection_notebook = ttk.Notebook(right_frame)
        self.connection_notebook.pack(fill=tk.BOTH, expand=True)

        # Bind tab close handlers
        self.connection_notebook.bind('<Button-2>', self._on_tab_middle_click)  # Middle-click
        self.connection_notebook.bind('<Button-3>', self._on_tab_right_click)   # Right-click

        # Welcome tab (shown when no connections are open)
        self._create_welcome_tab()

    def _create_welcome_tab(self):
        """Create the welcome/empty state tab"""
        welcome_frame = ttk.Frame(self.connection_notebook)
        self.connection_notebook.add(welcome_frame, text="Welcome")

        # Center content
        center_frame = ttk.Frame(welcome_frame)
        center_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        ttk.Label(center_frame, text="OdooBench", font=('TkDefaultFont', 24, 'bold')).pack(pady=10)
        ttk.Label(center_frame, text="Odoo Instance Manager", font=('TkDefaultFont', 12)).pack(pady=5)

        ttk.Label(center_frame, text="\nDouble-click a connection to open it,\nor create a new connection to get started.",
                  justify=tk.CENTER).pack(pady=20)

        ttk.Button(center_frame, text="New Connection", command=self._new_connection).pack(pady=10)

    def _refresh_connection_tree(self):
        """Refresh the connection tree view"""
        # Clear existing items
        for item in self.conn_tree.get_children():
            self.conn_tree.delete(item)

        # Get instances grouped
        groups = self.instance_manager.list_instances_by_group()

        # Add groups and connections
        for group_name, instances in sorted(groups.items()):
            # Add group node
            group_id = self.conn_tree.insert('', tk.END, text=f"  {group_name}",
                                              open=True, tags=('group',))

            # Add instances under group
            for instance in instances:
                # Determine icon/prefix based on connection state
                prefix = "  "
                if instance['id'] in self.open_connections:
                    prefix = "  "  # Connected indicator would go here

                # Show production warning
                name = instance['name']
                if instance['is_production']:
                    name = f"{name} [PROD]"

                self.conn_tree.insert(group_id, tk.END, text=f"{prefix}{name}",
                                       values=(instance['id'],),
                                       tags=('instance',))

        # Configure tags
        self.conn_tree.tag_configure('group', font=('TkDefaultFont', 9, 'bold'))

    def _on_connection_double_click(self, event):
        """Handle double-click on connection"""
        self._connect_selected()

    def _on_connection_right_click(self, event):
        """Show context menu on right-click"""
        item = self.conn_tree.identify_row(event.y)
        if item:
            self.conn_tree.selection_set(item)
            tags = self.conn_tree.item(item, 'tags')
            if 'instance' in tags:
                self.conn_context_menu.post(event.x_root, event.y_root)

    def _get_selected_instance_id(self) -> Optional[int]:
        """Get the ID of the selected instance"""
        selection = self.conn_tree.selection()
        if not selection:
            return None

        item = selection[0]
        tags = self.conn_tree.item(item, 'tags')
        if 'instance' not in tags:
            return None

        values = self.conn_tree.item(item, 'values')
        if values:
            return int(values[0])
        return None

    def _connect_selected(self):
        """Connect to the selected instance"""
        instance_id = self._get_selected_instance_id()
        if instance_id is None:
            return

        # Check if already connected
        if instance_id in self.open_connections:
            # Switch to existing tab
            tab = self.open_connections[instance_id]['tab_frame']
            self.connection_notebook.select(tab)
            return

        # Get instance details
        instance = self.instance_manager.get_instance(instance_id)
        if instance is None:
            messagebox.showerror("Error", "Instance not found")
            return

        # Create executor and connect
        self._open_connection(instance)

    def _open_connection(self, instance: Dict[str, Any]):
        """Open a connection tab for an instance"""
        instance_id = instance['id']

        # Create executor
        exec_config = self.instance_manager.get_executor_config(instance_id)
        try:
            executor = create_executor(exec_config)
        except Exception as e:
            messagebox.showerror("Connection Error", f"Failed to connect:\n{e}")
            return

        # Create the connection tab
        tab_frame = ttk.Frame(self.connection_notebook)
        self.connection_notebook.add(tab_frame, text=f"  {instance['name']}  ")

        # Create feature notebook inside
        feature_notebook = ttk.Notebook(tab_frame)
        feature_notebook.pack(fill=tk.BOTH, expand=True)

        # Store connection info
        self.open_connections[instance_id] = {
            'instance': instance,
            'executor': executor,
            'tab_frame': tab_frame,
            'feature_notebook': feature_notebook,
            'tabs': {},
        }

        # Create feature tabs
        self._create_logs_tab(instance_id)
        self._create_database_tab(instance_id)
        self._create_backup_tab(instance_id)
        # Restore tab only shown if this connection allows restore (as destination)
        if instance.get('allow_restore'):
            self._create_restore_tab(instance_id)
        # Backup & Restore always available (backup FROM here, restore TO another)
        self._create_backup_restore_tab(instance_id)
        # Operation History tab
        self._create_history_tab(instance_id)
        # Future: modules, config, health tabs

        # Switch to the new tab
        self.connection_notebook.select(tab_frame)

        # Refresh tree to show connected state
        self._refresh_connection_tree()

    def _on_tab_middle_click(self, event):
        """Handle middle-click to close tab"""
        instance_id = self._get_tab_instance_id_at(event.x, event.y)
        if instance_id is not None:
            self._close_connection(instance_id)

    def _on_tab_right_click(self, event):
        """Handle right-click to show tab context menu"""
        instance_id = self._get_tab_instance_id_at(event.x, event.y)
        if instance_id is None:
            return

        # Create context menu
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Close Tab", command=lambda: self._close_connection(instance_id))
        menu.add_command(label="Close Other Tabs", command=lambda: self._close_other_tabs(instance_id))
        menu.add_command(label="Close All Tabs", command=self._close_all_tabs)

        # Bind events to close menu when clicking elsewhere or pressing Escape
        def close_menu(e=None):
            menu.unpost()
            menu.destroy()

        menu.bind('<FocusOut>', close_menu)
        menu.bind('<Escape>', close_menu)

        # Show menu
        menu.tk_popup(event.x_root, event.y_root, 0)

    def _get_tab_instance_id_at(self, x: int, y: int) -> Optional[int]:
        """Get the instance_id for the tab at the given coordinates"""
        try:
            clicked_tab_index = self.connection_notebook.index(f"@{x},{y}")
            if clicked_tab_index == 0:  # Welcome tab
                return None

            # Get the tab frame at this index
            tab_id = self.connection_notebook.tabs()[clicked_tab_index]
            tab_frame = self.connection_notebook.nametowidget(tab_id)

            # Find which instance this tab belongs to
            for instance_id, conn_info in self.open_connections.items():
                if conn_info['tab_frame'] == tab_frame:
                    return instance_id
        except Exception:
            pass
        return None

    def _close_other_tabs(self, keep_instance_id: int):
        """Close all tabs except the specified one"""
        ids_to_close = [iid for iid in self.open_connections.keys() if iid != keep_instance_id]
        for instance_id in ids_to_close:
            self._close_connection(instance_id)

    def _close_all_tabs(self):
        """Close all connection tabs"""
        ids_to_close = list(self.open_connections.keys())
        for instance_id in ids_to_close:
            self._close_connection(instance_id)

    def _add_text_context_menu(self, text_widget: tk.Text):
        """Add a right-click context menu with Select All, Copy, Cut, Paste to a Text widget"""
        def show_context_menu(event):
            menu = tk.Menu(self.root, tearoff=0)

            # Check if text widget is editable
            is_disabled = str(text_widget.cget('state')) == 'disabled'

            # Select All - always available
            def select_all():
                text_widget.tag_add(tk.SEL, "1.0", tk.END)
                text_widget.mark_set(tk.INSERT, "1.0")
                text_widget.see(tk.INSERT)
            menu.add_command(label="Select All", command=select_all, accelerator="Ctrl+A")

            # Copy - always available
            def copy_text():
                try:
                    text_widget.event_generate("<<Copy>>")
                except tk.TclError:
                    pass
            menu.add_command(label="Copy", command=copy_text, accelerator="Ctrl+C")

            # Cut - only if editable and has selection
            def cut_text():
                try:
                    text_widget.event_generate("<<Cut>>")
                except tk.TclError:
                    pass
            if not is_disabled:
                menu.add_command(label="Cut", command=cut_text, accelerator="Ctrl+X")

            # Paste - only if editable
            def paste_text():
                try:
                    text_widget.event_generate("<<Paste>>")
                except tk.TclError:
                    pass
            if not is_disabled:
                menu.add_command(label="Paste", command=paste_text, accelerator="Ctrl+V")

            # Close menu on focus out
            def close_menu(e=None):
                menu.unpost()
                menu.destroy()

            menu.bind('<FocusOut>', close_menu)
            menu.bind('<Escape>', close_menu)

            menu.tk_popup(event.x_root, event.y_root, 0)

        text_widget.bind('<Button-3>', show_context_menu)

        # Also bind keyboard shortcuts
        def on_select_all(event):
            text_widget.tag_add(tk.SEL, "1.0", tk.END)
            text_widget.mark_set(tk.INSERT, "1.0")
            text_widget.see(tk.INSERT)
            return "break"

        text_widget.bind('<Control-a>', on_select_all)
        text_widget.bind('<Control-A>', on_select_all)

    def _set_operation_buttons_state(self, instance_id: int, state):
        """Enable or disable all operation buttons for a connection"""
        if instance_id not in self.open_connections:
            return

        conn_info = self.open_connections[instance_id]
        tabs = conn_info.get('tabs', {})

        # Backup tab button
        backup_widgets = tabs.get('backup_widgets', {})
        if 'start_btn' in backup_widgets:
            backup_widgets['start_btn'].configure(state=state)

        # Restore tab button
        restore_widgets = tabs.get('restore_widgets', {})
        if 'start_btn' in restore_widgets:
            restore_widgets['start_btn'].configure(state=state)

        # Backup & Restore tab button
        br_widgets = tabs.get('backup_restore_widgets', {})
        if 'start_btn' in br_widgets:
            br_widgets['start_btn'].configure(state=state)

    def _close_connection(self, instance_id: int, force: bool = False):
        """Close a connection and its tab"""
        if instance_id not in self.open_connections:
            return

        conn_info = self.open_connections[instance_id]

        # Check if an operation is running
        if not force and conn_info.get('operation_running'):
            instance_name = conn_info['instance'].get('name', 'Unknown')
            if not messagebox.askyesno(
                "Operation In Progress",
                f"A backup/restore operation is currently running on '{instance_name}'.\n\n"
                "Closing this tab will NOT stop the operation, but you will lose "
                "visibility of its progress and logs.\n\n"
                "Are you sure you want to close this tab?",
                icon='warning'
            ):
                return

        # Disconnect executor
        try:
            conn_info['executor'].disconnect()
        except:
            pass

        # Remove tab
        self.connection_notebook.forget(conn_info['tab_frame'])

        # Clean up
        del self.open_connections[instance_id]

        # Refresh tree
        self._refresh_connection_tree()

    def _create_logs_tab(self, instance_id: int):
        """Create the Logs feature tab"""
        conn_info = self.open_connections[instance_id]
        feature_notebook = conn_info['feature_notebook']
        instance = conn_info['instance']
        executor = conn_info['executor']

        tab = ttk.Frame(feature_notebook)
        feature_notebook.add(tab, text="Logs")
        conn_info['tabs']['logs'] = tab

        # Toolbar
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill=tk.X, padx=5, pady=5)

        # Log path
        ttk.Label(toolbar, text="Log file:").pack(side=tk.LEFT)
        log_path_var = tk.StringVar(value=instance.get('log_path', ''))
        log_path_entry = ttk.Entry(toolbar, textvariable=log_path_var, width=50)
        log_path_entry.pack(side=tk.LEFT, padx=5)

        # Lines to load
        ttk.Label(toolbar, text="Lines:").pack(side=tk.LEFT, padx=(10, 0))
        lines_var = tk.StringVar(value="500")
        lines_combo = ttk.Combobox(toolbar, textvariable=lines_var, width=8,
                                    values=['100', '500', '1000', '5000', '10000'])
        lines_combo.pack(side=tk.LEFT, padx=5)

        # Load button
        load_btn = ttk.Button(toolbar, text="Load", command=lambda: self._load_logs(instance_id))
        load_btn.pack(side=tk.LEFT, padx=5)

        # Follow checkbox
        follow_var = tk.BooleanVar(value=False)
        follow_check = ttk.Checkbutton(toolbar, text="Follow", variable=follow_var,
                                        command=lambda: self._toggle_log_follow(instance_id))
        follow_check.pack(side=tk.LEFT, padx=10)

        # Filter toolbar
        filter_frame = ttk.Frame(tab)
        filter_frame.pack(fill=tk.X, padx=5, pady=2)

        ttk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT)
        filter_var = tk.StringVar()
        filter_entry = ttk.Entry(filter_frame, textvariable=filter_var, width=30)
        filter_entry.pack(side=tk.LEFT, padx=5)
        # Filter as you type (with slight delay to avoid filtering on every keystroke)
        filter_var.trace_add('write', lambda *args: self._schedule_log_filter(instance_id))

        # Level filter
        ttk.Label(filter_frame, text="Level:").pack(side=tk.LEFT, padx=(10, 0))
        level_var = tk.StringVar(value="ALL")
        level_combo = ttk.Combobox(filter_frame, textvariable=level_var, width=10,
                                    values=['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
        level_combo.pack(side=tk.LEFT, padx=5)
        level_combo.bind('<<ComboboxSelected>>', lambda e: self._apply_log_filter(instance_id))

        # Clear button
        ttk.Button(filter_frame, text="Clear Filter",
                   command=lambda: self._clear_log_filter(instance_id)).pack(side=tk.LEFT, padx=5)

        # Find section (right side)
        ttk.Separator(filter_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill=tk.Y)
        ttk.Label(filter_frame, text="Find:").pack(side=tk.LEFT)
        find_var = tk.StringVar()
        find_entry = ttk.Entry(filter_frame, textvariable=find_var, width=20)
        find_entry.pack(side=tk.LEFT, padx=5)
        find_entry.bind('<Return>', lambda e: self._find_in_log(instance_id, forward=True))
        ttk.Button(filter_frame, text="↑", width=2,
                   command=lambda: self._find_in_log(instance_id, forward=False)).pack(side=tk.LEFT)
        ttk.Button(filter_frame, text="↓", width=2,
                   command=lambda: self._find_in_log(instance_id, forward=True)).pack(side=tk.LEFT)

        # Log text area with scrollbar
        log_frame = ttk.Frame(tab)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Apply dark mode colors to log text if needed
        is_dark = self.dark_mode_var.get()
        if is_dark:
            text_bg = "#313335"
            text_fg = "#a9b7c6"
        else:
            text_bg = "#ffffff"
            text_fg = "#000000"

        log_text = tk.Text(log_frame, wrap=tk.NONE, font='TkFixedFont',
                           bg=text_bg, fg=text_fg, insertbackground=text_fg)
        log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._add_text_context_menu(log_text)

        # Scrollbars
        y_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=log_text.yview)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        log_text.configure(yscrollcommand=y_scroll.set)

        x_scroll = ttk.Scrollbar(tab, orient=tk.HORIZONTAL, command=log_text.xview)
        x_scroll.pack(fill=tk.X, padx=5)
        log_text.configure(xscrollcommand=x_scroll.set)

        # Configure text tags for log levels
        log_text.tag_configure('ERROR', foreground='#ff6b6b')
        log_text.tag_configure('WARNING', foreground='#ffa500')
        log_text.tag_configure('INFO', foreground='#69db7c')
        log_text.tag_configure('DEBUG', foreground='#868e96')
        log_text.tag_configure('CRITICAL', foreground='#ff6b6b', underline=True)
        log_text.tag_configure('highlight', background='#ffd43b' if not is_dark else '#5c5c00')

        # Context menu for log text
        log_context_menu = tk.Menu(log_text, tearoff=0)
        log_context_menu.add_command(label="Select All", accelerator="Ctrl+A",
                                      command=lambda: self._log_select_all(log_text))
        log_context_menu.add_separator()
        log_context_menu.add_command(label="Copy", accelerator="Ctrl+C",
                                      command=lambda: self._log_copy(log_text))
        log_context_menu.add_command(label="Cut", accelerator="Ctrl+X",
                                      command=lambda: self._log_cut(log_text))
        log_context_menu.add_command(label="Paste", accelerator="Ctrl+V",
                                      command=lambda: self._log_paste(log_text))

        def show_log_context_menu(event):
            log_context_menu.post(event.x_root, event.y_root)

        log_text.bind('<Button-3>', show_log_context_menu)

        # Keyboard shortcuts
        log_text.bind('<Control-a>', lambda e: self._log_select_all(log_text))
        log_text.bind('<Control-c>', lambda e: self._log_copy(log_text))
        log_text.bind('<Control-f>', lambda e: find_entry.focus_set())
        find_entry.bind('<Control-f>', lambda e: self._find_in_log(instance_id, forward=True))
        find_entry.bind('<Shift-Return>', lambda e: self._find_in_log(instance_id, forward=False))

        # Store references
        conn_info['tabs']['logs_widgets'] = {
            'log_path_var': log_path_var,
            'lines_var': lines_var,
            'follow_var': follow_var,
            'filter_var': filter_var,
            'level_var': level_var,
            'find_entry': find_entry,
            'find_var': find_var,
            'find_pos': '1.0',  # Current find position
            'log_text': log_text,
            'all_logs': [],  # Store all log lines for filtering
        }

    def _load_logs(self, instance_id: int):
        """Load logs from the server"""
        if instance_id not in self.open_connections:
            return

        conn_info = self.open_connections[instance_id]
        widgets = conn_info['tabs'].get('logs_widgets', {})
        executor = conn_info['executor']

        log_path = widgets['log_path_var'].get()
        lines = int(widgets['lines_var'].get())
        log_text = widgets['log_text']

        if not log_path:
            messagebox.showwarning("Warning", "Please specify a log file path")
            return

        def load():
            try:
                content = executor.tail_file(log_path, lines)
                log_lines = content.split('\n')

                # Store all logs
                widgets['all_logs'] = log_lines

                # Update UI in main thread
                self.root.after(0, lambda: self._display_logs(instance_id, log_lines))

            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to load logs:\n{e}"))

        threading.Thread(target=load, daemon=True).start()

    def _display_logs(self, instance_id: int, log_lines: list):
        """Display log lines in the text widget"""
        if instance_id not in self.open_connections:
            return

        conn_info = self.open_connections[instance_id]
        widgets = conn_info['tabs'].get('logs_widgets', {})
        log_text = widgets['log_text']

        log_text.configure(state=tk.NORMAL)
        log_text.delete('1.0', tk.END)

        for line in log_lines:
            # Determine log level
            tag = None
            if ' ERROR ' in line or line.startswith('ERROR'):
                tag = 'ERROR'
            elif ' WARNING ' in line or line.startswith('WARNING'):
                tag = 'WARNING'
            elif ' INFO ' in line or line.startswith('INFO'):
                tag = 'INFO'
            elif ' DEBUG ' in line or line.startswith('DEBUG'):
                tag = 'DEBUG'
            elif ' CRITICAL ' in line:
                tag = 'CRITICAL'

            if tag:
                log_text.insert(tk.END, line + '\n', tag)
            else:
                log_text.insert(tk.END, line + '\n')

        log_text.configure(state=tk.DISABLED)
        log_text.see(tk.END)

    def _toggle_log_follow(self, instance_id: int):
        """Toggle log following mode"""
        if instance_id not in self.open_connections:
            return

        conn_info = self.open_connections[instance_id]
        widgets = conn_info['tabs'].get('logs_widgets', {})
        executor = conn_info['executor']
        follow = widgets['follow_var'].get()
        log_path = widgets['log_path_var'].get()
        log_text = widgets['log_text']

        if follow:
            # Start following
            def on_line(line):
                self.root.after(0, lambda l=line: self._append_log_line(instance_id, l))

            executor.tail_file_follow(log_path, on_line)
        else:
            # Stop following
            executor.stop_tail()

    def _append_log_line(self, instance_id: int, line: str):
        """Append a single log line (for follow mode)"""
        if instance_id not in self.open_connections:
            return

        conn_info = self.open_connections[instance_id]
        widgets = conn_info['tabs'].get('logs_widgets', {})
        log_text = widgets['log_text']

        # Also store in all_logs for filtering
        if 'all_logs' in widgets:
            widgets['all_logs'].append(line)

        # Determine tag
        tag = None
        if ' ERROR ' in line:
            tag = 'ERROR'
        elif ' WARNING ' in line:
            tag = 'WARNING'
        elif ' INFO ' in line:
            tag = 'INFO'
        elif ' DEBUG ' in line:
            tag = 'DEBUG'

        log_text.configure(state=tk.NORMAL)
        if tag:
            log_text.insert(tk.END, line + '\n', tag)
        else:
            log_text.insert(tk.END, line + '\n')
        log_text.configure(state=tk.DISABLED)
        log_text.see(tk.END)

    def _schedule_log_filter(self, instance_id: int):
        """Schedule a log filter with debounce to avoid filtering on every keystroke"""
        if instance_id not in self.open_connections:
            return

        conn_info = self.open_connections[instance_id]
        widgets = conn_info['tabs'].get('logs_widgets', {})

        # Cancel any pending filter
        if 'filter_after_id' in widgets and widgets['filter_after_id']:
            self.root.after_cancel(widgets['filter_after_id'])

        # Schedule filter after 150ms delay
        widgets['filter_after_id'] = self.root.after(150, lambda: self._apply_log_filter(instance_id))

    def _apply_log_filter(self, instance_id: int):
        """Apply filter to logs"""
        if instance_id not in self.open_connections:
            return

        conn_info = self.open_connections[instance_id]
        widgets = conn_info['tabs'].get('logs_widgets', {})

        filter_text = widgets['filter_var'].get().lower()
        level = widgets['level_var'].get()
        all_logs = widgets.get('all_logs', [])

        # Group lines into log entries (an entry starts with a timestamp pattern)
        # Odoo log format: "2025-12-04 03:54:04,773 PID LEVEL ..."
        import re
        timestamp_pattern = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}')

        log_entries = []
        current_entry = []

        for line in all_logs:
            if timestamp_pattern.match(line):
                # This is a new log entry
                if current_entry:
                    log_entries.append(current_entry)
                current_entry = [line]
            else:
                # Continuation line (traceback, etc.)
                current_entry.append(line)

        # Don't forget the last entry
        if current_entry:
            log_entries.append(current_entry)

        # Filter entries
        filtered = []
        for entry in log_entries:
            first_line = entry[0] if entry else ''

            # Level filter - check only the first line (the actual log line)
            if level != 'ALL':
                if level not in first_line:
                    continue

            # Text filter - check entire entry (including traceback)
            entry_text = '\n'.join(entry).lower()
            if filter_text and filter_text not in entry_text:
                continue

            # Include all lines of this entry
            filtered.extend(entry)

        self._display_logs(instance_id, filtered)

    def _clear_log_filter(self, instance_id: int):
        """Clear log filter"""
        if instance_id not in self.open_connections:
            return

        conn_info = self.open_connections[instance_id]
        widgets = conn_info['tabs'].get('logs_widgets', {})

        widgets['filter_var'].set('')
        widgets['level_var'].set('ALL')
        self._display_logs(instance_id, widgets.get('all_logs', []))

    def _find_in_log(self, instance_id: int, forward: bool = True):
        """Find text in log and highlight it"""
        if instance_id not in self.open_connections:
            return

        conn_info = self.open_connections[instance_id]
        widgets = conn_info['tabs'].get('logs_widgets', {})
        log_text = widgets['log_text']
        search_text = widgets['find_var'].get()

        if not search_text:
            return

        # Remove previous highlight
        log_text.tag_remove('find_highlight', '1.0', tk.END)

        # Get current position
        current_pos = widgets.get('find_pos', '1.0')

        # Search for text
        if forward:
            # Start search from after current position
            start_pos = current_pos
            pos = log_text.search(search_text, start_pos, nocase=True, stopindex=tk.END)
            if not pos:
                # Wrap around to beginning
                pos = log_text.search(search_text, '1.0', nocase=True, stopindex=start_pos)
        else:
            # Search backwards
            start_pos = current_pos
            pos = log_text.search(search_text, start_pos, nocase=True, backwards=True, stopindex='1.0')
            if not pos:
                # Wrap around to end
                pos = log_text.search(search_text, tk.END, nocase=True, backwards=True, stopindex=start_pos)

        if pos:
            # Highlight the found text
            end_pos = f"{pos}+{len(search_text)}c"
            log_text.tag_add('find_highlight', pos, end_pos)
            log_text.tag_config('find_highlight', background='yellow', foreground='black')

            # Scroll to show the found text
            log_text.see(pos)

            # Update position for next search
            if forward:
                widgets['find_pos'] = end_pos
            else:
                widgets['find_pos'] = pos

    def _log_select_all(self, log_text: tk.Text):
        """Select all text in log widget"""
        log_text.tag_add(tk.SEL, "1.0", tk.END)
        log_text.mark_set(tk.INSERT, "1.0")
        log_text.see(tk.INSERT)
        return 'break'  # Prevent default behavior

    def _log_copy(self, log_text: tk.Text):
        """Copy selected text to clipboard"""
        try:
            selected = log_text.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.root.clipboard_clear()
            self.root.clipboard_append(selected)
        except tk.TclError:
            pass  # No selection
        return 'break'

    def _log_cut(self, log_text: tk.Text):
        """Cut selected text (copy only since log is read-only)"""
        self._log_copy(log_text)
        return 'break'

    def _log_paste(self, log_text: tk.Text):
        """Paste is disabled for read-only log"""
        pass  # Log is read-only, paste does nothing

    def _create_database_tab(self, instance_id: int):
        """Create the Database feature tab"""
        conn_info = self.open_connections[instance_id]
        feature_notebook = conn_info['feature_notebook']
        instance = conn_info['instance']

        tab = ttk.Frame(feature_notebook)
        feature_notebook.add(tab, text="Database")
        conn_info['tabs']['database'] = tab

        # Get theme colors
        is_dark = self.dark_mode_var.get()
        if is_dark:
            text_bg = "#1e1e1e"
            text_fg = "#d4d4d4"
        else:
            text_bg = "#ffffff"
            text_fg = "#000000"

        # Connection info frame (compact, top)
        info_frame = ttk.LabelFrame(tab, text="Connection", padding=5)
        info_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        info_inner = ttk.Frame(info_frame)
        info_inner.pack(fill=tk.X)
        col = 0
        for label, key in [("Host:", 'db_host'), ("Port:", 'db_port'),
                           ("User:", 'db_user'), ("Database:", 'db_name')]:
            ttk.Label(info_inner, text=label).grid(row=0, column=col, sticky=tk.W, padx=(10, 2))
            ttk.Label(info_inner, text=str(instance.get(key, 'N/A')),
                      font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=col+1, sticky=tk.W, padx=(0, 15))
            col += 2

        # Actions frame
        actions_frame = ttk.Frame(tab)
        actions_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(actions_frame, text="Refresh All",
                   command=lambda: self._refresh_database_info(instance_id)).pack(side=tk.LEFT, padx=5)
        ttk.Button(actions_frame, text="Test Connection",
                   command=lambda: self._test_db_connection(instance_id)).pack(side=tk.LEFT, padx=5)
        ttk.Button(actions_frame, text="List Databases",
                   command=lambda: self._list_databases(instance_id)).pack(side=tk.LEFT, padx=5)

        # PostgreSQL Version label
        version_label = ttk.Label(actions_frame, text="PostgreSQL: --")
        version_label.pack(side=tk.RIGHT, padx=10)

        # Health Dashboard frame
        health_frame = ttk.LabelFrame(tab, text="Health Dashboard", padding=10)
        health_frame.pack(fill=tk.X, padx=10, pady=5)

        # Create health metrics grid
        health_grid = ttk.Frame(health_frame)
        health_grid.pack(fill=tk.X)

        # Row 1: Key metrics
        health_labels = {}
        metrics = [
            ('db_size', 'Database Size:', '--'),
            ('cache_ratio', 'Cache Hit Ratio:', '--'),
            ('connections', 'Connections:', '--'),
            ('vacuum_needed', 'Tables Need Vacuum:', '--'),
        ]
        for col, (key, label, default) in enumerate(metrics):
            frame = ttk.Frame(health_grid)
            frame.grid(row=0, column=col, padx=10, pady=5, sticky=tk.W)
            ttk.Label(frame, text=label).pack(anchor=tk.W)
            value_label = ttk.Label(frame, text=default, font=('TkDefaultFont', 11, 'bold'))
            value_label.pack(anchor=tk.W)
            health_labels[key] = value_label

        # PostgreSQL Settings frame
        settings_frame = ttk.LabelFrame(tab, text="PostgreSQL Settings", padding=10)
        settings_frame.pack(fill=tk.X, padx=10, pady=5)

        # Create settings treeview
        settings_tree = ttk.Treeview(settings_frame,
                                      columns=('setting', 'current', 'recommended', 'status'),
                                      show='headings', height=9)
        settings_tree.heading('setting', text='Setting')
        settings_tree.heading('current', text='Current Value')
        settings_tree.heading('recommended', text='Recommended')
        settings_tree.heading('status', text='Status')
        settings_tree.column('setting', width=200, anchor=tk.W)
        settings_tree.column('current', width=150, anchor=tk.E)
        settings_tree.column('recommended', width=150, anchor=tk.E)
        settings_tree.column('status', width=100, anchor=tk.CENTER)

        settings_tree.pack(fill=tk.X, expand=True)

        # Configure tags for status colors
        settings_tree.tag_configure('good', foreground='#28a745')
        settings_tree.tag_configure('warning', foreground='#ffc107')
        settings_tree.tag_configure('bad', foreground='#dc3545')
        settings_tree.tag_configure('info', foreground=text_fg)

        # Server memory label
        memory_label = ttk.Label(settings_frame, text="Server RAM: -- (recommendations based on detected RAM)")
        memory_label.pack(anchor=tk.W, pady=(5, 0))

        # Top Tables frame (vacuum status)
        tables_frame = ttk.LabelFrame(tab, text="Table Maintenance Status", padding=10)
        tables_frame.pack(fill=tk.X, padx=10, pady=5)

        tables_tree = ttk.Treeview(tables_frame,
                                    columns=('table', 'last_vacuum', 'last_autovacuum', 'last_analyze'),
                                    show='headings', height=5)
        tables_tree.heading('table', text='Table')
        tables_tree.heading('last_vacuum', text='Last Vacuum')
        tables_tree.heading('last_autovacuum', text='Last Auto-Vacuum')
        tables_tree.heading('last_analyze', text='Last Analyze')
        tables_tree.column('table', width=200, anchor=tk.W)
        tables_tree.column('last_vacuum', width=150, anchor=tk.W)
        tables_tree.column('last_autovacuum', width=150, anchor=tk.W)
        tables_tree.column('last_analyze', width=150, anchor=tk.W)

        tables_tree.pack(fill=tk.X, expand=True)

        # Results/Messages area - this one expands to fill remaining space
        results_frame = ttk.LabelFrame(tab, text="Messages", padding=10)
        results_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))

        results_text = tk.Text(results_frame, height=4, font='TkFixedFont',
                               bg=text_bg, fg=text_fg)
        results_text.pack(fill=tk.BOTH, expand=True)
        self._add_text_context_menu(results_text)

        conn_info['tabs']['database_widgets'] = {
            'results_text': results_text,
            'version_label': version_label,
            'health_labels': health_labels,
            'settings_tree': settings_tree,
            'memory_label': memory_label,
            'tables_tree': tables_tree,
        }

        # Auto-refresh on tab creation
        self.root.after(500, lambda: self._refresh_database_info(instance_id))

    def _test_db_connection(self, instance_id: int):
        """Test database connection"""
        if instance_id not in self.open_connections:
            return

        conn_info = self.open_connections[instance_id]
        instance = conn_info['instance']
        executor = conn_info['executor']
        widgets = conn_info['tabs'].get('database_widgets', {})
        results_text = widgets['results_text']

        def test():
            parser = OdooConfigParser(executor)
            success, message = parser.test_database_connection(
                db_host=instance.get('db_host', 'localhost'),
                db_port=instance.get('db_port', 5432),
                db_user=instance.get('db_user', 'odoo'),
                db_password=instance.get('db_password', ''),
            )
            self.root.after(0, lambda: self._show_db_result(results_text, message))

        threading.Thread(target=test, daemon=True).start()

    def _list_databases(self, instance_id: int):
        """List available databases"""
        if instance_id not in self.open_connections:
            return

        conn_info = self.open_connections[instance_id]
        instance = conn_info['instance']
        executor = conn_info['executor']
        widgets = conn_info['tabs'].get('database_widgets', {})
        results_text = widgets['results_text']

        def list_dbs():
            parser = OdooConfigParser(executor)
            databases = parser.get_databases(
                db_host=instance.get('db_host', 'localhost'),
                db_port=instance.get('db_port', 5432),
                db_user=instance.get('db_user', 'odoo'),
                db_password=instance.get('db_password', ''),
            )
            result = "Available databases:\n\n" + "\n".join(f"  - {db}" for db in databases)
            self.root.after(0, lambda: self._show_db_result(results_text, result))

        threading.Thread(target=list_dbs, daemon=True).start()

    def _show_db_result(self, text_widget, message: str):
        """Show result in database results text widget"""
        text_widget.configure(state=tk.NORMAL)
        text_widget.delete('1.0', tk.END)
        text_widget.insert('1.0', message)
        text_widget.configure(state=tk.DISABLED)

    def _refresh_database_info(self, instance_id: int):
        """Refresh all database information"""
        if instance_id not in self.open_connections:
            return

        conn_info = self.open_connections[instance_id]
        instance = conn_info['instance']
        executor = conn_info['executor']
        widgets = conn_info['tabs'].get('database_widgets', {})

        if not widgets:
            return

        results_text = widgets.get('results_text')
        if results_text:
            self._show_db_result(results_text, "Fetching database information...")

        def fetch_info():
            parser = OdooConfigParser(executor)

            db_host = instance.get('db_host', 'localhost')
            db_port = instance.get('db_port', 5432)
            db_user = instance.get('db_user', 'odoo')
            db_password = instance.get('db_password', '')
            db_name = instance.get('db_name', '') or 'postgres'

            # Fetch all data
            version = parser.get_postgresql_version(db_host, db_port, db_user, db_password)
            settings = parser.get_postgresql_settings(db_host, db_port, db_user, db_password, db_name)
            stats = parser.get_database_stats(db_host, db_port, db_user, db_password, db_name)
            server_ram = parser.get_server_memory()

            # Update UI on main thread
            self.root.after(0, lambda: self._update_database_display(
                instance_id, version, settings, stats, server_ram
            ))

        threading.Thread(target=fetch_info, daemon=True).start()

    def _update_database_display(self, instance_id: int, version: str, settings: dict,
                                  stats: dict, server_ram: int):
        """Update the database tab display with fetched data"""
        if instance_id not in self.open_connections:
            return

        conn_info = self.open_connections[instance_id]
        widgets = conn_info['tabs'].get('database_widgets', {})

        if not widgets:
            return

        # Update version label
        version_label = widgets.get('version_label')
        if version_label and version:
            # Extract just the version number
            match = re.search(r'PostgreSQL (\d+\.\d+)', version)
            if match:
                version_label.configure(text=f"PostgreSQL: {match.group(1)}")
            else:
                version_label.configure(text=f"PostgreSQL: {version[:30]}...")

        # Update health labels
        health_labels = widgets.get('health_labels', {})

        if 'db_size' in stats and health_labels.get('db_size'):
            size_bytes = stats['db_size']
            size_str = self._format_bytes(size_bytes)
            health_labels['db_size'].configure(text=size_str)

        if 'cache_hit_ratio' in stats and health_labels.get('cache_ratio'):
            ratio = stats['cache_hit_ratio']
            color = '#28a745' if ratio >= 99 else '#ffc107' if ratio >= 95 else '#dc3545'
            health_labels['cache_ratio'].configure(text=f"{ratio}%", foreground=color)

        if 'active_connections' in stats and health_labels.get('connections'):
            active = stats.get('active_connections', 0)
            max_conn = stats.get('max_connections', 100)
            pct = (active / max_conn * 100) if max_conn > 0 else 0
            color = '#28a745' if pct < 50 else '#ffc107' if pct < 80 else '#dc3545'
            health_labels['connections'].configure(text=f"{active} / {max_conn}", foreground=color)

        if 'tables_needing_vacuum' in stats and health_labels.get('vacuum_needed'):
            count = stats['tables_needing_vacuum']
            color = '#28a745' if count == 0 else '#ffc107' if count < 5 else '#dc3545'
            health_labels['vacuum_needed'].configure(text=str(count), foreground=color)

        # Update settings tree
        settings_tree = widgets.get('settings_tree')
        if settings_tree and not settings.get('error'):
            # Clear existing items
            for item in settings_tree.get_children():
                settings_tree.delete(item)

            # Calculate recommendations based on server RAM
            recommendations = self._calculate_pg_recommendations(server_ram)

            # Settings to display with their recommendations
            settings_info = [
                ('shared_buffers', 'Shared Buffers', 'shared_buffers'),
                ('effective_cache_size', 'Effective Cache Size', 'effective_cache_size'),
                ('work_mem', 'Work Memory', 'work_mem'),
                ('maintenance_work_mem', 'Maintenance Work Memory', 'maintenance_work_mem'),
                ('max_connections', 'Max Connections', 'max_connections'),
                ('random_page_cost', 'Random Page Cost', 'random_page_cost'),
                ('effective_io_concurrency', 'Effective I/O Concurrency', 'effective_io_concurrency'),
                ('checkpoint_completion_target', 'Checkpoint Completion Target', 'checkpoint_completion_target'),
                ('wal_buffers', 'WAL Buffers', 'wal_buffers'),
            ]

            for setting_key, display_name, rec_key in settings_info:
                if setting_key in settings:
                    setting = settings[setting_key]
                    current = self._format_pg_setting(setting['value'], setting['unit'])
                    recommended = recommendations.get(rec_key, 'N/A')
                    status, tag = self._evaluate_pg_setting(setting_key, setting, recommendations)

                    settings_tree.insert('', tk.END, values=(display_name, current, recommended, status), tags=(tag,))

        # Update memory label
        memory_label = widgets.get('memory_label')
        if memory_label and server_ram:
            ram_str = self._format_bytes(server_ram)
            memory_label.configure(text=f"Server RAM: {ram_str} (recommendations based on detected RAM)")
        elif memory_label:
            memory_label.configure(text="Server RAM: Unknown (using conservative recommendations)")

        # Update tables tree
        tables_tree = widgets.get('tables_tree')
        if tables_tree and 'top_tables' in stats:
            for item in tables_tree.get_children():
                tables_tree.delete(item)

            for table in stats['top_tables']:
                tables_tree.insert('', tk.END, values=(
                    table['name'],
                    self._format_timestamp(table['last_vacuum']),
                    self._format_timestamp(table['last_autovacuum']),
                    self._format_timestamp(table['last_analyze']),
                ))

        # Update results text
        results_text = widgets.get('results_text')
        if results_text:
            if settings.get('error'):
                self._show_db_result(results_text, f"Error fetching settings: {settings['error']}")
            else:
                self._show_db_result(results_text, "Database information refreshed successfully.")

    def _format_bytes(self, bytes_val: int) -> str:
        """Format bytes to human readable string"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if abs(bytes_val) < 1024:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024
        return f"{bytes_val:.1f} PB"

    def _format_pg_setting(self, value: str, unit: str) -> str:
        """Format a PostgreSQL setting value with its unit"""
        try:
            val = float(value)
            if unit == '8kB':
                # Convert to MB for readability
                mb = (val * 8) / 1024
                if mb >= 1024:
                    return f"{mb / 1024:.1f} GB"
                return f"{mb:.0f} MB"
            elif unit == 'kB':
                if val >= 1024:
                    return f"{val / 1024:.0f} MB"
                return f"{val:.0f} KB"
            elif unit == 'MB':
                if val >= 1024:
                    return f"{val / 1024:.1f} GB"
                return f"{val:.0f} MB"
            elif unit:
                return f"{value} {unit}"
            else:
                return value
        except (ValueError, TypeError):
            return f"{value} {unit}" if unit else value

    def _format_timestamp(self, ts: str) -> str:
        """Format a timestamp for display"""
        if not ts or ts == 'Never':
            return 'Never'
        # Truncate to just date and time
        if ' ' in ts:
            parts = ts.split('.')
            return parts[0] if parts else ts
        return ts

    def _calculate_pg_recommendations(self, server_ram: int) -> dict:
        """Calculate recommended PostgreSQL settings based on server RAM"""
        recommendations = {}

        if server_ram:
            ram_gb = server_ram / (1024 ** 3)

            # shared_buffers: ~25% of RAM, max ~8GB for most workloads
            shared_gb = min(ram_gb * 0.25, 8)
            if shared_gb >= 1:
                recommendations['shared_buffers'] = f"{shared_gb:.1f} GB"
            else:
                recommendations['shared_buffers'] = f"{int(shared_gb * 1024)} MB"

            # effective_cache_size: ~50-75% of RAM
            cache_gb = ram_gb * 0.5
            recommendations['effective_cache_size'] = f"{cache_gb:.1f} GB"

            # work_mem: depends on max_connections, typically 16-64MB
            recommendations['work_mem'] = "32 MB"

            # maintenance_work_mem: 256MB to 1GB
            maint_mb = min(max(256, ram_gb * 64), 1024)
            recommendations['maintenance_work_mem'] = f"{int(maint_mb)} MB"
        else:
            # Conservative defaults when RAM is unknown
            recommendations['shared_buffers'] = "256 MB"
            recommendations['effective_cache_size'] = "1 GB"
            recommendations['work_mem'] = "16 MB"
            recommendations['maintenance_work_mem'] = "256 MB"

        # Fixed recommendations
        recommendations['max_connections'] = "100-200"
        recommendations['random_page_cost'] = "1.1 (SSD)"
        recommendations['effective_io_concurrency'] = "200 (SSD)"
        recommendations['checkpoint_completion_target'] = "0.9"
        recommendations['wal_buffers'] = "64 MB"

        return recommendations

    def _evaluate_pg_setting(self, setting_name: str, setting: dict, recommendations: dict) -> tuple:
        """Evaluate if a PostgreSQL setting is optimal, returns (status_text, tag)"""
        try:
            value = float(setting['value'])
            unit = setting['unit']

            # Convert to common unit (MB) for comparison
            if unit == '8kB':
                value_mb = (value * 8) / 1024
            elif unit == 'kB':
                value_mb = value / 1024
            elif unit == 'MB':
                value_mb = value
            else:
                value_mb = value

            if setting_name == 'shared_buffers':
                # shared_buffers should be at least 256MB
                if value_mb >= 256:
                    return ('Good', 'good')
                elif value_mb >= 128:
                    return ('Low', 'warning')
                else:
                    return ('Too Low', 'bad')

            elif setting_name == 'effective_cache_size':
                # Should be at least 1GB
                if value_mb >= 1024:
                    return ('Good', 'good')
                elif value_mb >= 512:
                    return ('Low', 'warning')
                else:
                    return ('Too Low', 'bad')

            elif setting_name == 'work_mem':
                # 4-64MB is reasonable
                if 4 <= value_mb <= 128:
                    return ('Good', 'good')
                elif value_mb < 4:
                    return ('Too Low', 'warning')
                else:
                    return ('High', 'warning')

            elif setting_name == 'maintenance_work_mem':
                if value_mb >= 256:
                    return ('Good', 'good')
                elif value_mb >= 64:
                    return ('OK', 'warning')
                else:
                    return ('Low', 'bad')

            elif setting_name == 'random_page_cost':
                # 1.1 for SSD, 4.0 for HDD
                if value <= 1.5:
                    return ('SSD', 'good')
                elif value <= 2.0:
                    return ('OK', 'info')
                else:
                    return ('HDD Default', 'warning')

            elif setting_name == 'effective_io_concurrency':
                if value >= 100:
                    return ('SSD', 'good')
                elif value >= 2:
                    return ('OK', 'info')
                else:
                    return ('Default', 'warning')

            elif setting_name == 'checkpoint_completion_target':
                if value >= 0.9:
                    return ('Good', 'good')
                elif value >= 0.7:
                    return ('OK', 'info')
                else:
                    return ('Low', 'warning')

            elif setting_name == 'max_connections':
                if 50 <= value <= 200:
                    return ('Good', 'good')
                elif value > 200:
                    return ('High', 'warning')
                else:
                    return ('Low', 'warning')

            elif setting_name == 'wal_buffers':
                if value_mb >= 16:
                    return ('Good', 'good')
                else:
                    return ('Default', 'info')

        except (ValueError, TypeError, KeyError):
            pass

        return ('--', 'info')

    def _create_backup_tab(self, instance_id: int):
        """Create the Backup feature tab"""
        conn_info = self.open_connections[instance_id]
        feature_notebook = conn_info['feature_notebook']
        instance = conn_info['instance']

        tab = ttk.Frame(feature_notebook)
        feature_notebook.add(tab, text="Backup")
        conn_info['tabs']['backup'] = tab

        # Apply dark mode colors
        is_dark = self.dark_mode_var.get()
        text_bg = "#313335" if is_dark else "#ffffff"
        text_fg = "#a9b7c6" if is_dark else "#000000"

        # Source info frame
        source_frame = ttk.LabelFrame(tab, text="Backup Source", padding=10)
        source_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        info_grid = ttk.Frame(source_frame)
        info_grid.pack(fill=tk.X)

        row = 0
        for label, value in [("Database:", instance.get('db_name', 'Not specified')),
                              ("Host:", instance.get('db_host', 'localhost')),
                              ("Filestore:", instance.get('filestore_path', 'Not specified'))]:
            ttk.Label(info_grid, text=label, font=('TkDefaultFont', 9, 'bold')).grid(row=row, column=0, sticky=tk.W, padx=5, pady=2)
            ttk.Label(info_grid, text=value).grid(row=row, column=1, sticky=tk.W, padx=5, pady=2)
            row += 1

        # Backup options frame
        options_frame = ttk.LabelFrame(tab, text="Backup Options", padding=10)
        options_frame.pack(fill=tk.X, padx=10, pady=5)

        # Backup type
        type_frame = ttk.Frame(options_frame)
        type_frame.pack(fill=tk.X, pady=5)

        ttk.Label(type_frame, text="Backup Type:").pack(side=tk.LEFT, padx=(0, 10))

        backup_type_var = tk.StringVar(value="complete")
        ttk.Radiobutton(type_frame, text="Complete (DB + Filestore)", variable=backup_type_var,
                        value="complete").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(type_frame, text="Database Only", variable=backup_type_var,
                        value="db_only").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(type_frame, text="Filestore Only", variable=backup_type_var,
                        value="filestore_only").pack(side=tk.LEFT)

        # Backup destination
        dest_frame = ttk.Frame(options_frame)
        dest_frame.pack(fill=tk.X, pady=10)

        ttk.Label(dest_frame, text="Save to:").pack(side=tk.LEFT, padx=(0, 10))
        backup_dir_var = tk.StringVar(value=self.backup_directory)
        backup_dir_entry = ttk.Entry(dest_frame, textvariable=backup_dir_var, width=50)
        backup_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        def browse_backup_dir():
            path = filedialog.askdirectory(
                title="Select Backup Directory",
                initialdir=backup_dir_var.get()
            )
            if path:
                backup_dir_var.set(path)

        ttk.Button(dest_frame, text="Browse...", command=browse_backup_dir).pack(side=tk.LEFT)

        # Start backup button
        btn_frame = ttk.Frame(options_frame)
        btn_frame.pack(fill=tk.X, pady=10)

        def start_backup():
            self._run_backup(instance_id, backup_type_var.get(), backup_dir_var.get())

        start_btn = ttk.Button(btn_frame, text="Start Backup", command=start_backup)
        start_btn.pack(side=tk.LEFT)

        # Progress frame
        progress_frame = ttk.LabelFrame(tab, text="Progress", padding=10)
        progress_frame.pack(fill=tk.X, padx=10, pady=5)

        progress_var = tk.DoubleVar(value=0)
        progress_bar = ttk.Progressbar(progress_frame, variable=progress_var, maximum=100)
        progress_bar.pack(fill=tk.X, pady=(0, 5))

        status_var = tk.StringVar(value="Ready")
        ttk.Label(progress_frame, textvariable=status_var).pack(anchor=tk.W)

        # Log output frame
        log_frame = ttk.LabelFrame(tab, text="Backup Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))

        log_text = tk.Text(log_frame, height=12, font='TkFixedFont',
                           bg=text_bg, fg=text_fg, insertbackground=text_fg)
        log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._add_text_context_menu(log_text)

        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        log_text.configure(yscrollcommand=log_scroll.set)
        log_text.configure(state=tk.DISABLED)

        # Configure log tags
        log_text.tag_configure('error', foreground='#ff6b6b')
        log_text.tag_configure('warning', foreground='#ffa500')
        log_text.tag_configure('success', foreground='#69db7c')
        log_text.tag_configure('info', foreground=text_fg)

        # Store widgets
        conn_info['tabs']['backup_widgets'] = {
            'backup_type_var': backup_type_var,
            'backup_dir_var': backup_dir_var,
            'progress_var': progress_var,
            'status_var': status_var,
            'log_text': log_text,
            'start_btn': start_btn,
        }

    def _run_backup(self, instance_id: int, backup_type: str, backup_dir: str):
        """Run backup operation"""
        if instance_id not in self.open_connections:
            return

        conn_info = self.open_connections[instance_id]
        instance = conn_info['instance']
        widgets = conn_info['tabs'].get('backup_widgets', {})

        # Validate
        db_name = instance.get('db_name')
        if not db_name:
            messagebox.showwarning("Warning", "No database specified for this connection.")
            return

        if backup_type != 'db_only' and not instance.get('filestore_path'):
            if not messagebox.askyesno("Warning",
                                        "No filestore path specified.\n\n"
                                        "Continue with database-only backup?"):
                return
            backup_type = 'db_only'

        # Create backup directory if needed
        if not os.path.exists(backup_dir):
            try:
                os.makedirs(backup_dir, exist_ok=True)
            except Exception as e:
                messagebox.showerror("Error", f"Cannot create backup directory:\n{e}")
                return

        # Clear log
        log_text = widgets['log_text']
        log_text.configure(state=tk.NORMAL)
        log_text.delete('1.0', tk.END)
        log_text.configure(state=tk.DISABLED)

        def log_callback(message, level="info"):
            def update():
                log_text.configure(state=tk.NORMAL)
                log_text.insert(tk.END, message + "\n", level)
                log_text.configure(state=tk.DISABLED)
                log_text.see(tk.END)
            self.root.after(0, update)

        def progress_callback(value, message=""):
            def update():
                widgets['progress_var'].set(value)
                if message:
                    widgets['status_var'].set(message)
            self.root.after(0, update)

        def do_backup():
            log_lines = []  # Capture all log lines for saving
            backup_path = None
            import time
            start_time = time.time()

            def capture_log(message, level="info"):
                log_lines.append(message)
                log_callback(message, level)

            try:
                progress_callback(0, "Starting backup...")

                # Log operation details
                capture_log("=== Backup Operation ===", "info")
                capture_log(f"Connection: {instance.get('name', 'Unknown')}", "info")
                capture_log(f"Database: {instance.get('db_name')} @ {instance.get('db_host', 'localhost')}:{instance.get('db_port', 5432)}", "info")
                capture_log(f"Backup Type: {backup_type.replace('_', ' ').title()}", "info")
                capture_log(f"Backup Directory: {backup_dir}", "info")
                capture_log(f"Filestore Path: {instance.get('filestore_path') or '(not configured)'}", "info")
                capture_log(f"Remote: {'Yes (SSH)' if not instance.get('is_local') else 'No (Local)'}", "info")
                capture_log("", "info")

                # Build backup config
                config = {
                    'db_name': instance['db_name'],
                    'db_host': instance.get('db_host', 'localhost'),
                    'db_port': instance.get('db_port', 5432),
                    'db_user': instance.get('db_user', 'odoo'),
                    'db_password': instance.get('db_password', ''),
                    'filestore_path': instance.get('filestore_path', ''),
                    'backup_dir': backup_dir,
                    'db_only': backup_type == 'db_only',
                    'filestore_only': backup_type == 'filestore_only',
                }

                # Add SSH connection if remote
                if not instance.get('is_local'):
                    config['use_ssh'] = True
                    config['ssh_connection_id'] = instance['id']

                bench = OdooBench(
                    progress_callback=progress_callback,
                    log_callback=capture_log,
                    conn_manager=self.instance_manager
                )

                backup_path = bench.backup(config)
                progress_callback(100, f"Backup complete!")
                capture_log(f"\nBackup saved to: {backup_path}", "success")

                # Log total operation time
                elapsed = time.time() - start_time
                minutes, seconds = divmod(int(elapsed), 60)
                if minutes > 0:
                    capture_log(f"\nTotal operation time: {minutes}m {seconds}s", "info")
                else:
                    capture_log(f"\nTotal operation time: {seconds}s", "info")

                # Save operation log
                self.instance_manager.save_operation_log(
                    instance_id=instance_id,
                    operation_type='backup',
                    status='success',
                    log_text='\n'.join(log_lines),
                    backup_file=backup_path
                )

                # Refresh Recent Backups lists in all open Restore tabs
                self.root.after(0, self._refresh_all_recent_backups)

                self.root.after(0, lambda: messagebox.showinfo(
                    "Backup Complete",
                    f"Backup saved to:\n{backup_path}"
                ))

            except Exception as e:
                capture_log(f"\nBackup failed: {str(e)}", "error")

                # Log total operation time even on failure
                elapsed = time.time() - start_time
                minutes, seconds = divmod(int(elapsed), 60)
                if minutes > 0:
                    capture_log(f"\nTotal operation time: {minutes}m {seconds}s", "info")
                else:
                    capture_log(f"\nTotal operation time: {seconds}s", "info")

                progress_callback(0, "Backup failed")

                # Save operation log (failed)
                self.instance_manager.save_operation_log(
                    instance_id=instance_id,
                    operation_type='backup',
                    status='failed',
                    log_text='\n'.join(log_lines),
                    backup_file=backup_path
                )

                self.root.after(0, lambda: messagebox.showerror("Backup Failed", str(e)))

            finally:
                # Clear operation running flag and re-enable buttons
                if instance_id in self.open_connections:
                    self.open_connections[instance_id]['operation_running'] = False
                self.root.after(0, lambda: self._set_operation_buttons_state(instance_id, tk.NORMAL))

        # Run in background thread
        conn_info['operation_running'] = True
        self._set_operation_buttons_state(instance_id, tk.DISABLED)
        widgets['status_var'].set("Starting backup...")
        threading.Thread(target=do_backup, daemon=True).start()

    def _create_restore_tab(self, instance_id: int):
        """Create the Restore feature tab"""
        conn_info = self.open_connections[instance_id]
        feature_notebook = conn_info['feature_notebook']
        instance = conn_info['instance']

        tab = ttk.Frame(feature_notebook)
        feature_notebook.add(tab, text="Restore")
        conn_info['tabs']['restore'] = tab

        # Apply dark mode colors
        is_dark = self.dark_mode_var.get()
        text_bg = "#313335" if is_dark else "#ffffff"
        text_fg = "#a9b7c6" if is_dark else "#000000"

        # Production warning
        if instance.get('is_production'):
            warning_frame = ttk.Frame(tab)
            warning_frame.pack(fill=tk.X, padx=10, pady=10)
            warning_label = ttk.Label(warning_frame,
                                       text="WARNING: This is a PRODUCTION instance!",
                                       foreground='#ff6b6b', font=('TkDefaultFont', 11, 'bold'))
            warning_label.pack()

        # Target info frame
        target_frame = ttk.LabelFrame(tab, text="Restore Target", padding=10)
        target_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        info_grid = ttk.Frame(target_frame)
        info_grid.pack(fill=tk.X)

        row = 0
        for label, value in [("Database:", instance.get('db_name', 'Not specified')),
                              ("Host:", instance.get('db_host', 'localhost')),
                              ("Filestore:", instance.get('filestore_path', 'Not specified'))]:
            ttk.Label(info_grid, text=label, font=('TkDefaultFont', 9, 'bold')).grid(row=row, column=0, sticky=tk.W, padx=5, pady=2)
            ttk.Label(info_grid, text=value).grid(row=row, column=1, sticky=tk.W, padx=5, pady=2)
            row += 1

        # Backup file selection
        file_frame = ttk.LabelFrame(tab, text="Backup File", padding=10)
        file_frame.pack(fill=tk.X, padx=10, pady=5)

        file_row = ttk.Frame(file_frame)
        file_row.pack(fill=tk.X)

        ttk.Label(file_row, text="File:").pack(side=tk.LEFT, padx=(0, 10))
        backup_file_var = tk.StringVar()
        backup_file_entry = ttk.Entry(file_row, textvariable=backup_file_var, width=50)
        backup_file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        def browse_backup_file():
            path = filedialog.askopenfilename(
                title="Select Backup File",
                initialdir=self.backup_directory,
                filetypes=[
                    ("Backup files", "*.tar.gz *.zip *.tar"),
                    ("All files", "*.*")
                ]
            )
            if path:
                backup_file_var.set(path)

        ttk.Button(file_row, text="Browse...", command=browse_backup_file).pack(side=tk.LEFT)

        # Recent backups list
        recent_frame = ttk.Frame(file_frame)
        recent_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Label(recent_frame, text="Recent backups in backup directory:").pack(anchor=tk.W)

        # Listbox for recent backups
        list_frame = ttk.Frame(recent_frame)
        list_frame.pack(fill=tk.X, pady=5)

        recent_listbox = tk.Listbox(list_frame, height=4, font='TkFixedFont',
                                     bg=text_bg, fg=text_fg,
                                     selectbackground="#214283" if is_dark else "#0078d4")
        recent_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)

        list_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=recent_listbox.yview)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        recent_listbox.configure(yscrollcommand=list_scroll.set)

        def refresh_recent():
            recent_listbox.delete(0, tk.END)
            if os.path.exists(self.backup_directory):
                files = []
                for f in os.listdir(self.backup_directory):
                    if f.endswith(('.tar.gz', '.zip', '.tar')):
                        full_path = os.path.join(self.backup_directory, f)
                        mtime = os.path.getmtime(full_path)
                        files.append((f, mtime))
                files.sort(key=lambda x: x[1], reverse=True)
                for f, _ in files[:10]:  # Show top 10
                    recent_listbox.insert(tk.END, f)

        def on_select_recent(event):
            selection = recent_listbox.curselection()
            if selection:
                filename = recent_listbox.get(selection[0])
                backup_file_var.set(os.path.join(self.backup_directory, filename))

        recent_listbox.bind('<<ListboxSelect>>', on_select_recent)
        recent_listbox.bind('<Double-1>', on_select_recent)

        ttk.Button(recent_frame, text="Refresh", command=refresh_recent).pack(anchor=tk.W)

        # Restore options
        options_frame = ttk.LabelFrame(tab, text="Restore Options", padding=10)
        options_frame.pack(fill=tk.X, padx=10, pady=5)

        # Restore type
        type_frame = ttk.Frame(options_frame)
        type_frame.pack(fill=tk.X, pady=5)

        ttk.Label(type_frame, text="Restore:").pack(side=tk.LEFT, padx=(0, 10))

        restore_type_var = tk.StringVar(value="complete")
        ttk.Radiobutton(type_frame, text="Complete (DB + Filestore)", variable=restore_type_var,
                        value="complete").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(type_frame, text="Database Only", variable=restore_type_var,
                        value="db_only").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(type_frame, text="Filestore Only", variable=restore_type_var,
                        value="filestore_only").pack(side=tk.LEFT)

        # Neutralization option
        neutralize_frame = ttk.Frame(options_frame)
        neutralize_frame.pack(fill=tk.X, pady=10)

        neutralize_var = tk.BooleanVar(value=True)
        neutralize_check = ttk.Checkbutton(neutralize_frame, text="Neutralize database after restore",
                                            variable=neutralize_var)
        neutralize_check.pack(anchor=tk.W)

        ttk.Label(neutralize_frame, text="  (Disables email servers, crons, payment providers, prefixes company names with [TEST])",
                  foreground='gray').pack(anchor=tk.W)

        # Start restore button
        btn_frame = ttk.Frame(options_frame)
        btn_frame.pack(fill=tk.X, pady=10)

        def start_restore():
            self._run_restore(instance_id, backup_file_var.get(),
                             restore_type_var.get(), neutralize_var.get())

        start_btn = ttk.Button(btn_frame, text="Start Restore", command=start_restore)
        start_btn.pack(side=tk.LEFT)

        # Progress frame
        progress_frame = ttk.LabelFrame(tab, text="Progress", padding=10)
        progress_frame.pack(fill=tk.X, padx=10, pady=5)

        progress_var = tk.DoubleVar(value=0)
        progress_bar = ttk.Progressbar(progress_frame, variable=progress_var, maximum=100)
        progress_bar.pack(fill=tk.X, pady=(0, 5))

        status_var = tk.StringVar(value="Ready")
        ttk.Label(progress_frame, textvariable=status_var).pack(anchor=tk.W)

        # Log output frame
        log_frame = ttk.LabelFrame(tab, text="Restore Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))

        log_text = tk.Text(log_frame, height=8, font='TkFixedFont',
                           bg=text_bg, fg=text_fg, insertbackground=text_fg)
        log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._add_text_context_menu(log_text)

        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        log_text.configure(yscrollcommand=log_scroll.set)
        log_text.configure(state=tk.DISABLED)

        # Configure log tags
        log_text.tag_configure('error', foreground='#ff6b6b')
        log_text.tag_configure('warning', foreground='#ffa500')
        log_text.tag_configure('success', foreground='#69db7c')
        log_text.tag_configure('info', foreground=text_fg)

        # Store widgets
        conn_info['tabs']['restore_widgets'] = {
            'backup_file_var': backup_file_var,
            'restore_type_var': restore_type_var,
            'neutralize_var': neutralize_var,
            'progress_var': progress_var,
            'status_var': status_var,
            'log_text': log_text,
            'recent_listbox': recent_listbox,
            'refresh_recent': refresh_recent,  # Store for external refresh calls
            'start_btn': start_btn,
        }

        # Initial refresh of recent backups
        refresh_recent()

    def _run_restore(self, instance_id: int, backup_file: str, restore_type: str, neutralize: bool):
        """Run restore operation"""
        if instance_id not in self.open_connections:
            return

        conn_info = self.open_connections[instance_id]
        instance = conn_info['instance']
        widgets = conn_info['tabs'].get('restore_widgets', {})

        # Validate backup file
        if not backup_file:
            messagebox.showwarning("Warning", "Please select a backup file.")
            return

        if not os.path.exists(backup_file):
            messagebox.showerror("Error", f"Backup file not found:\n{backup_file}")
            return

        # Validate target database
        db_name = instance.get('db_name')
        if not db_name and restore_type != 'filestore_only':
            messagebox.showwarning("Warning", "No database specified for this connection.")
            return

        # Production confirmation
        if instance.get('is_production'):
            if not messagebox.askyesno("Production Warning",
                                        "You are about to restore to a PRODUCTION instance!\n\n"
                                        f"Database: {db_name}\n"
                                        f"Host: {instance.get('db_host', 'localhost')}\n\n"
                                        "This will OVERWRITE all existing data.\n\n"
                                        "Are you absolutely sure you want to continue?",
                                        icon='warning'):
                return

            # Double confirmation for production
            confirm = messagebox.askquestion("Final Confirmation",
                                              f"Type the database name to confirm:\n\n"
                                              f"This will delete all data in: {db_name}",
                                              icon='warning')
            if confirm != 'yes':
                return

        # Standard confirmation
        else:
            if not messagebox.askyesno("Confirm Restore",
                                        f"This will restore:\n\n"
                                        f"From: {os.path.basename(backup_file)}\n"
                                        f"To: {db_name} @ {instance.get('db_host', 'localhost')}\n\n"
                                        f"Neutralize: {'Yes' if neutralize else 'No'}\n\n"
                                        "Existing data will be OVERWRITTEN.\n"
                                        "Continue?"):
                return

        # Clear log
        log_text = widgets['log_text']
        log_text.configure(state=tk.NORMAL)
        log_text.delete('1.0', tk.END)
        log_text.configure(state=tk.DISABLED)

        def log_callback(message, level="info"):
            def update():
                log_text.configure(state=tk.NORMAL)
                log_text.insert(tk.END, message + "\n", level)
                log_text.configure(state=tk.DISABLED)
                log_text.see(tk.END)
            self.root.after(0, update)

        def progress_callback(value, message=""):
            def update():
                widgets['progress_var'].set(value)
                if message:
                    widgets['status_var'].set(message)
            self.root.after(0, update)

        def do_restore():
            log_lines = []  # Capture all log lines for saving
            import time
            start_time = time.time()

            def capture_log(message, level="info"):
                log_lines.append(message)
                log_callback(message, level)

            try:
                progress_callback(0, "Starting restore...")

                # Log operation details
                capture_log("=== Restore Operation ===", "info")
                capture_log(f"Connection: {instance.get('name', 'Unknown')}", "info")
                capture_log(f"Database: {instance.get('db_name')} @ {instance.get('db_host', 'localhost')}:{instance.get('db_port', 5432)}", "info")
                capture_log(f"Backup File: {backup_file}", "info")
                capture_log(f"Restore Type: {restore_type.replace('_', ' ').title()}", "info")
                capture_log(f"Neutralize: {'Yes' if neutralize else 'No'}", "info")
                capture_log(f"Filestore Path: {instance.get('filestore_path') or '(not configured)'}", "info")
                capture_log(f"Remote: {'Yes (SSH)' if not instance.get('is_local') else 'No (Local)'}", "info")
                capture_log(f"Production: {'Yes' if instance.get('is_production') else 'No'}", "info")
                capture_log("", "info")

                # Build restore config
                config = {
                    'db_name': instance['db_name'],
                    'db_host': instance.get('db_host', 'localhost'),
                    'db_port': instance.get('db_port', 5432),
                    'db_user': instance.get('db_user', 'odoo'),
                    'db_password': instance.get('db_password', ''),
                    'filestore_path': instance.get('filestore_path', ''),
                    'neutralize': neutralize,
                    'db_only': restore_type == 'db_only',
                    'filestore_only': restore_type == 'filestore_only',
                }

                # Add SSH connection if remote
                if not instance.get('is_local'):
                    config['use_ssh'] = True
                    config['ssh_connection_id'] = instance['id']

                bench = OdooBench(
                    progress_callback=progress_callback,
                    log_callback=capture_log,
                    conn_manager=self.instance_manager
                )

                bench.restore(config, backup_file)
                progress_callback(100, "Restore complete!")
                capture_log("\nRestore completed successfully!", "success")

                # Log total operation time
                elapsed = time.time() - start_time
                minutes, seconds = divmod(int(elapsed), 60)
                if minutes > 0:
                    capture_log(f"\nTotal operation time: {minutes}m {seconds}s", "info")
                else:
                    capture_log(f"\nTotal operation time: {seconds}s", "info")

                # Save operation log
                self.instance_manager.save_operation_log(
                    instance_id=instance_id,
                    operation_type='restore',
                    status='success',
                    log_text='\n'.join(log_lines),
                    backup_file=backup_file
                )

                self.root.after(0, lambda: messagebox.showinfo(
                    "Restore Complete",
                    f"Database restored successfully.\n\n"
                    f"{'Database has been neutralized.' if neutralize else ''}"
                ))

            except Exception as e:
                capture_log(f"\nRestore failed: {str(e)}", "error")

                # Log total operation time even on failure
                elapsed = time.time() - start_time
                minutes, seconds = divmod(int(elapsed), 60)
                if minutes > 0:
                    capture_log(f"\nTotal operation time: {minutes}m {seconds}s", "info")
                else:
                    capture_log(f"\nTotal operation time: {seconds}s", "info")

                progress_callback(0, "Restore failed")

                # Save operation log (failed)
                self.instance_manager.save_operation_log(
                    instance_id=instance_id,
                    operation_type='restore',
                    status='failed',
                    log_text='\n'.join(log_lines),
                    backup_file=backup_file
                )

                self.root.after(0, lambda: messagebox.showerror("Restore Failed", str(e)))

            finally:
                # Clear operation running flag and re-enable buttons
                if instance_id in self.open_connections:
                    self.open_connections[instance_id]['operation_running'] = False
                self.root.after(0, lambda: self._set_operation_buttons_state(instance_id, tk.NORMAL))

        # Run in background thread
        conn_info['operation_running'] = True
        self._set_operation_buttons_state(instance_id, tk.DISABLED)
        widgets['status_var'].set("Starting restore...")
        threading.Thread(target=do_restore, daemon=True).start()

    def _create_backup_restore_tab(self, instance_id: int):
        """Create the Backup & Restore (one-shot) feature tab"""
        conn_info = self.open_connections[instance_id]
        feature_notebook = conn_info['feature_notebook']
        instance = conn_info['instance']

        tab = ttk.Frame(feature_notebook)
        feature_notebook.add(tab, text="Backup & Restore")
        conn_info['tabs']['backup_restore'] = tab

        # Apply dark mode colors
        is_dark = self.dark_mode_var.get()
        text_bg = "#313335" if is_dark else "#ffffff"
        text_fg = "#a9b7c6" if is_dark else "#000000"

        # Description
        desc_frame = ttk.Frame(tab)
        desc_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(desc_frame, text="Backup from this connection and restore to another in one operation",
                  font=('TkDefaultFont', 10)).pack(anchor=tk.W)

        # Source frame (current connection)
        source_frame = ttk.LabelFrame(tab, text="Source (This Connection)", padding=10)
        source_frame.pack(fill=tk.X, padx=10, pady=5)

        source_grid = ttk.Frame(source_frame)
        source_grid.pack(fill=tk.X)

        row = 0
        for label, value in [("Database:", instance.get('db_name', 'Not specified')),
                              ("Host:", instance.get('db_host', 'localhost')),
                              ("Filestore:", instance.get('filestore_path', 'Not specified'))]:
            ttk.Label(source_grid, text=label, font=('TkDefaultFont', 9, 'bold')).grid(row=row, column=0, sticky=tk.W, padx=5, pady=2)
            ttk.Label(source_grid, text=value).grid(row=row, column=1, sticky=tk.W, padx=5, pady=2)
            row += 1

        # Destination frame
        dest_frame = ttk.LabelFrame(tab, text="Destination", padding=10)
        dest_frame.pack(fill=tk.X, padx=10, pady=5)

        dest_row = ttk.Frame(dest_frame)
        dest_row.pack(fill=tk.X, pady=5)

        ttk.Label(dest_row, text="Restore to:").pack(side=tk.LEFT, padx=(0, 10))

        # Build list of other connections that allow restore
        dest_var = tk.StringVar()
        dest_combo = ttk.Combobox(dest_row, textvariable=dest_var, width=40, state='readonly')
        dest_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Destination info display
        dest_info_var = tk.StringVar(value="Select a destination connection")
        ttk.Label(dest_frame, textvariable=dest_info_var, foreground='gray').pack(anchor=tk.W, pady=(5, 0))

        def refresh_destinations():
            instances = self.instance_manager.list_instances()
            dest_options = []
            dest_map = {}
            for inst in instances:
                if inst['id'] != instance_id:  # Exclude current connection
                    full_inst = self.instance_manager.get_instance(inst['id'])
                    if full_inst and full_inst.get('allow_restore'):
                        label = f"{inst['name']} ({inst.get('db_name', 'N/A')} @ {inst.get('host', 'localhost')})"
                        dest_options.append(label)
                        dest_map[label] = inst['id']
            dest_combo['values'] = dest_options
            conn_info['tabs']['backup_restore_widgets']['dest_map'] = dest_map

            if not dest_options:
                dest_info_var.set("No connections with restore enabled. Enable restore on a connection first.")

        def on_dest_selected(event):
            selected = dest_var.get()
            dest_map = conn_info['tabs']['backup_restore_widgets'].get('dest_map', {})
            if selected in dest_map:
                dest_id = dest_map[selected]
                dest_inst = self.instance_manager.get_instance(dest_id)
                if dest_inst:
                    info = f"DB: {dest_inst.get('db_name', 'N/A')} | Host: {dest_inst.get('db_host', 'localhost')} | Filestore: {dest_inst.get('filestore_path', 'N/A')}"
                    if dest_inst.get('is_production'):
                        info = "[PRODUCTION] " + info
                    dest_info_var.set(info)

        dest_combo.bind('<<ComboboxSelected>>', on_dest_selected)

        ttk.Button(dest_frame, text="Refresh", command=refresh_destinations).pack(anchor=tk.W, pady=(5, 0))

        # Options frame
        options_frame = ttk.LabelFrame(tab, text="Options", padding=10)
        options_frame.pack(fill=tk.X, padx=10, pady=5)

        # Backup type
        type_frame = ttk.Frame(options_frame)
        type_frame.pack(fill=tk.X, pady=5)

        ttk.Label(type_frame, text="Type:").pack(side=tk.LEFT, padx=(0, 10))

        br_type_var = tk.StringVar(value="complete")
        ttk.Radiobutton(type_frame, text="Complete (DB + Filestore)", variable=br_type_var,
                        value="complete").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(type_frame, text="Database Only", variable=br_type_var,
                        value="db_only").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(type_frame, text="Filestore Only", variable=br_type_var,
                        value="filestore_only").pack(side=tk.LEFT)

        # Neutralization
        neutralize_frame = ttk.Frame(options_frame)
        neutralize_frame.pack(fill=tk.X, pady=5)

        neutralize_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(neutralize_frame, text="Neutralize destination after restore",
                        variable=neutralize_var).pack(anchor=tk.W)
        ttk.Label(neutralize_frame, text="  (Disables email, crons, payments; prefixes company names with [TEST])",
                  foreground='gray').pack(anchor=tk.W)

        # Start button
        btn_frame = ttk.Frame(options_frame)
        btn_frame.pack(fill=tk.X, pady=10)

        def start_backup_restore():
            self._run_backup_restore(instance_id, dest_var.get(), br_type_var.get(), neutralize_var.get())

        start_btn = ttk.Button(btn_frame, text="Start Backup & Restore", command=start_backup_restore)
        start_btn.pack(side=tk.LEFT)

        # Progress frame
        progress_frame = ttk.LabelFrame(tab, text="Progress", padding=10)
        progress_frame.pack(fill=tk.X, padx=10, pady=5)

        progress_var = tk.DoubleVar(value=0)
        progress_bar = ttk.Progressbar(progress_frame, variable=progress_var, maximum=100)
        progress_bar.pack(fill=tk.X, pady=(0, 5))

        status_var = tk.StringVar(value="Ready")
        ttk.Label(progress_frame, textvariable=status_var).pack(anchor=tk.W)

        # Log output
        log_frame = ttk.LabelFrame(tab, text="Operation Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))

        log_text = tk.Text(log_frame, height=10, font='TkFixedFont',
                           bg=text_bg, fg=text_fg, insertbackground=text_fg)
        log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._add_text_context_menu(log_text)

        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        log_text.configure(yscrollcommand=log_scroll.set)
        log_text.configure(state=tk.DISABLED)

        # Configure log tags
        log_text.tag_configure('error', foreground='#ff6b6b')
        log_text.tag_configure('warning', foreground='#ffa500')
        log_text.tag_configure('success', foreground='#69db7c')
        log_text.tag_configure('info', foreground=text_fg)

        # Store widgets
        conn_info['tabs']['backup_restore_widgets'] = {
            'dest_var': dest_var,
            'dest_combo': dest_combo,
            'dest_info_var': dest_info_var,
            'br_type_var': br_type_var,
            'neutralize_var': neutralize_var,
            'progress_var': progress_var,
            'status_var': status_var,
            'log_text': log_text,
            'dest_map': {},
            'refresh_destinations': refresh_destinations,  # Store reference for external refresh
            'start_btn': start_btn,
        }

        # Initial refresh
        refresh_destinations()

    def _run_backup_restore(self, source_id: int, dest_selection: str, br_type: str, neutralize: bool):
        """Run backup and restore in one operation"""
        if source_id not in self.open_connections:
            return

        conn_info = self.open_connections[source_id]
        source_instance = conn_info['instance']
        widgets = conn_info['tabs'].get('backup_restore_widgets', {})

        # Validate destination
        if not dest_selection:
            messagebox.showwarning("Warning", "Please select a destination connection.")
            return

        dest_map = widgets.get('dest_map', {})
        if dest_selection not in dest_map:
            messagebox.showerror("Error", "Invalid destination selection.")
            return

        dest_id = dest_map[dest_selection]
        dest_instance = self.instance_manager.get_instance(dest_id)
        if not dest_instance:
            messagebox.showerror("Error", "Destination connection not found.")
            return

        # Validate source database
        if not source_instance.get('db_name') and br_type != 'filestore_only':
            messagebox.showwarning("Warning", "Source has no database specified.")
            return

        # Validate destination
        if not dest_instance.get('db_name') and br_type != 'filestore_only':
            messagebox.showwarning("Warning", "Destination has no database specified.")
            return

        if not dest_instance.get('allow_restore'):
            messagebox.showerror("Error", "Restore is not enabled for the destination connection.")
            return

        # Production warning
        if dest_instance.get('is_production'):
            if not messagebox.askyesno("Production Warning",
                                        f"The destination is a PRODUCTION instance!\n\n"
                                        f"Source: {source_instance.get('db_name')} @ {source_instance.get('db_host', 'localhost')}\n"
                                        f"Destination: {dest_instance.get('db_name')} @ {dest_instance.get('db_host', 'localhost')}\n\n"
                                        "This will OVERWRITE all data in the destination.\n\n"
                                        "Are you absolutely sure?",
                                        icon='warning'):
                return

        # Standard confirmation
        if not messagebox.askyesno("Confirm Backup & Restore",
                                    f"This will:\n\n"
                                    f"1. Backup from: {source_instance.get('db_name')} @ {source_instance.get('db_host', 'localhost')}\n"
                                    f"2. Restore to: {dest_instance.get('db_name')} @ {dest_instance.get('db_host', 'localhost')}\n\n"
                                    f"Type: {br_type.replace('_', ' ').title()}\n"
                                    f"Neutralize: {'Yes' if neutralize else 'No'}\n\n"
                                    "Continue?"):
            return

        # Clear log
        log_text = widgets['log_text']
        log_text.configure(state=tk.NORMAL)
        log_text.delete('1.0', tk.END)
        log_text.configure(state=tk.DISABLED)

        def log_callback(message, level="info"):
            def update():
                log_text.configure(state=tk.NORMAL)
                log_text.insert(tk.END, message + "\n", level)
                log_text.configure(state=tk.DISABLED)
                log_text.see(tk.END)
            self.root.after(0, update)

        def progress_callback(value, message=""):
            def update():
                widgets['progress_var'].set(value)
                if message:
                    widgets['status_var'].set(message)
            self.root.after(0, update)

        def do_backup_restore():
            log_lines = []  # Capture all log lines for saving
            backup_path = None
            import time
            start_time = time.time()

            def capture_log(message, level="info"):
                log_lines.append(message)
                log_callback(message, level)

            try:
                progress_callback(0, "Starting backup & restore...")

                # Log operation details
                capture_log("=== Backup & Restore Operation ===", "info")
                capture_log("", "info")
                capture_log("--- Source (Backup From) ---", "info")
                capture_log(f"Connection: {source_instance.get('name', 'Unknown')}", "info")
                capture_log(f"Database: {source_instance.get('db_name')} @ {source_instance.get('db_host', 'localhost')}:{source_instance.get('db_port', 5432)}", "info")
                capture_log(f"Filestore Path: {source_instance.get('filestore_path') or '(not configured)'}", "info")
                capture_log(f"Remote: {'Yes (SSH)' if not source_instance.get('is_local') else 'No (Local)'}", "info")
                capture_log("", "info")
                capture_log("--- Destination (Restore To) ---", "info")
                capture_log(f"Connection: {dest_instance.get('name', 'Unknown')}", "info")
                capture_log(f"Database: {dest_instance.get('db_name')} @ {dest_instance.get('db_host', 'localhost')}:{dest_instance.get('db_port', 5432)}", "info")
                capture_log(f"Filestore Path: {dest_instance.get('filestore_path') or '(not configured)'}", "info")
                capture_log(f"Remote: {'Yes (SSH)' if not dest_instance.get('is_local') else 'No (Local)'}", "info")
                capture_log(f"Production: {'Yes' if dest_instance.get('is_production') else 'No'}", "info")
                capture_log("", "info")
                capture_log("--- Options ---", "info")
                capture_log(f"Operation Type: {br_type.replace('_', ' ').title()}", "info")
                capture_log(f"Neutralize Destination: {'Yes' if neutralize else 'No'}", "info")
                capture_log(f"Backup Directory: {self.backup_directory}", "info")
                capture_log("", "info")

                # Build source config
                source_config = {
                    'db_name': source_instance['db_name'],
                    'db_host': source_instance.get('db_host', 'localhost'),
                    'db_port': source_instance.get('db_port', 5432),
                    'db_user': source_instance.get('db_user', 'odoo'),
                    'db_password': source_instance.get('db_password', ''),
                    'filestore_path': source_instance.get('filestore_path', ''),
                    'backup_dir': self.backup_directory,
                    'db_only': br_type == 'db_only',
                    'filestore_only': br_type == 'filestore_only',
                }

                if not source_instance.get('is_local'):
                    source_config['use_ssh'] = True
                    source_config['ssh_connection_id'] = source_id

                # Build destination config
                dest_config = {
                    'db_name': dest_instance['db_name'],
                    'db_host': dest_instance.get('db_host', 'localhost'),
                    'db_port': dest_instance.get('db_port', 5432),
                    'db_user': dest_instance.get('db_user', 'odoo'),
                    'db_password': dest_instance.get('db_password', ''),
                    'filestore_path': dest_instance.get('filestore_path', ''),
                    'neutralize': neutralize,
                    'db_only': br_type == 'db_only',
                    'filestore_only': br_type == 'filestore_only',
                }

                if not dest_instance.get('is_local'):
                    dest_config['use_ssh'] = True
                    dest_config['ssh_connection_id'] = dest_id

                bench = OdooBench(
                    progress_callback=progress_callback,
                    log_callback=capture_log,
                    conn_manager=self.instance_manager
                )

                # Perform backup and restore (returns backup file path)
                backup_path = bench.backup_and_restore(source_config, dest_config)

                progress_callback(100, "Backup & Restore complete!")
                capture_log("\n=== Operation Completed Successfully ===", "success")

                # Log total operation time
                elapsed = time.time() - start_time
                minutes, seconds = divmod(int(elapsed), 60)
                if minutes > 0:
                    capture_log(f"\nTotal operation time: {minutes}m {seconds}s", "info")
                else:
                    capture_log(f"\nTotal operation time: {seconds}s", "info")

                # Save operation log for source (backup)
                self.instance_manager.save_operation_log(
                    instance_id=source_id,
                    operation_type='backup_restore',
                    status='success',
                    log_text='\n'.join(log_lines),
                    backup_file=backup_path
                )

                # Also save operation log for destination (restore)
                self.instance_manager.save_operation_log(
                    instance_id=dest_id,
                    operation_type='backup_restore',
                    status='success',
                    log_text='\n'.join(log_lines),
                    backup_file=backup_path
                )

                # Refresh Recent Backups lists
                self.root.after(0, self._refresh_all_recent_backups)

                self.root.after(0, lambda: messagebox.showinfo(
                    "Backup & Restore Complete",
                    f"Successfully copied:\n\n"
                    f"From: {source_instance.get('db_name')}\n"
                    f"To: {dest_instance.get('db_name')}\n\n"
                    f"Backup saved to: {backup_path}\n\n"
                    f"{'Database has been neutralized.' if neutralize else ''}"
                ))

            except Exception as e:
                capture_log(f"\nOperation failed: {str(e)}", "error")
                if backup_path:
                    capture_log(f"Backup file preserved at: {backup_path}", "warning")

                # Log total operation time even on failure
                elapsed = time.time() - start_time
                minutes, seconds = divmod(int(elapsed), 60)
                if minutes > 0:
                    capture_log(f"\nTotal operation time: {minutes}m {seconds}s", "info")
                else:
                    capture_log(f"\nTotal operation time: {seconds}s", "info")

                progress_callback(0, "Operation failed")

                # Save operation log (failed) for source
                self.instance_manager.save_operation_log(
                    instance_id=source_id,
                    operation_type='backup_restore',
                    status='failed',
                    log_text='\n'.join(log_lines),
                    backup_file=backup_path
                )

                # Refresh Recent Backups if backup was created before failure
                if backup_path:
                    self.root.after(0, self._refresh_all_recent_backups)

                self.root.after(0, lambda: messagebox.showerror("Backup & Restore Failed", str(e)))

            finally:
                # Clear operation running flag and re-enable buttons
                if source_id in self.open_connections:
                    self.open_connections[source_id]['operation_running'] = False
                self.root.after(0, lambda: self._set_operation_buttons_state(source_id, tk.NORMAL))

        # Run in background thread
        conn_info['operation_running'] = True
        self._set_operation_buttons_state(source_id, tk.DISABLED)
        widgets['status_var'].set("Starting backup & restore...")
        threading.Thread(target=do_backup_restore, daemon=True).start()

    def _create_history_tab(self, instance_id: int):
        """Create the Operation History tab"""
        conn_info = self.open_connections[instance_id]
        feature_notebook = conn_info['feature_notebook']
        instance = conn_info['instance']

        tab = ttk.Frame(feature_notebook)
        feature_notebook.add(tab, text="History")
        conn_info['tabs']['history'] = tab

        # Apply dark mode colors
        is_dark = self.dark_mode_var.get()
        text_bg = "#313335" if is_dark else "#ffffff"
        text_fg = "#a9b7c6" if is_dark else "#000000"

        # Header
        header_frame = ttk.Frame(tab)
        header_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(header_frame, text="Operation History",
                  font=('TkDefaultFont', 12, 'bold')).pack(side=tk.LEFT)
        ttk.Button(header_frame, text="Refresh", command=lambda: refresh_history()).pack(side=tk.RIGHT)

        # Operations list frame
        list_frame = ttk.LabelFrame(tab, text="Past Operations", padding=10)
        list_frame.pack(fill=tk.X, padx=10, pady=5)

        # Treeview for operations
        columns = ('date', 'type', 'status', 'backup_file')
        ops_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=8)
        ops_tree.heading('date', text='Date/Time')
        ops_tree.heading('type', text='Operation')
        ops_tree.heading('status', text='Status')
        ops_tree.heading('backup_file', text='Backup File')

        ops_tree.column('date', width=150)
        ops_tree.column('type', width=100)
        ops_tree.column('status', width=80)
        ops_tree.column('backup_file', width=300)

        ops_tree.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tree_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=ops_tree.yview)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        ops_tree.configure(yscrollcommand=tree_scroll.set)

        # Log detail frame
        detail_frame = ttk.LabelFrame(tab, text="Operation Log", padding=10)
        detail_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))

        log_text = tk.Text(detail_frame, height=12, font='TkFixedFont',
                           bg=text_bg, fg=text_fg, insertbackground=text_fg)
        log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._add_text_context_menu(log_text)

        log_scroll = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL, command=log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        log_text.configure(yscrollcommand=log_scroll.set)
        log_text.configure(state=tk.DISABLED)

        # Configure log tags
        log_text.tag_configure('error', foreground='#ff6b6b')
        log_text.tag_configure('warning', foreground='#ffa500')
        log_text.tag_configure('success', foreground='#69db7c')
        log_text.tag_configure('info', foreground=text_fg)

        # Store logs data for selection
        logs_data = {}

        def refresh_history():
            """Refresh the operation history list"""
            ops_tree.delete(*ops_tree.get_children())
            logs_data.clear()

            logs = self.instance_manager.get_operation_logs(instance_id=instance_id, limit=50)
            for log in logs:
                log_id = log['id']
                # Format date
                completed = log.get('completed_at', '')
                if completed:
                    try:
                        # Parse and format the date
                        from datetime import datetime
                        dt = datetime.fromisoformat(completed.replace('Z', '+00:00'))
                        date_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        date_str = completed
                else:
                    date_str = 'Unknown'

                # Format operation type
                op_type = log.get('operation_type', '').replace('_', ' ').title()

                # Format status with indicator
                status = log.get('status', '')
                status_display = '✓ ' + status.title() if status == 'success' else '✗ ' + status.title()

                # Get backup filename only
                backup_file = log.get('backup_file', '')
                if backup_file:
                    backup_file = os.path.basename(backup_file)

                item_id = ops_tree.insert('', 'end', values=(date_str, op_type, status_display, backup_file))
                logs_data[item_id] = log

        def on_select_operation(event):
            """Show log details when an operation is selected"""
            selection = ops_tree.selection()
            if not selection:
                return

            item_id = selection[0]
            log = logs_data.get(item_id)
            if not log:
                return

            # Display log text
            log_text.configure(state=tk.NORMAL)
            log_text.delete('1.0', tk.END)

            log_content = log.get('log_text', 'No log content available')
            log_text.insert(tk.END, log_content)

            log_text.configure(state=tk.DISABLED)

        ops_tree.bind('<<TreeviewSelect>>', on_select_operation)

        # Store widgets
        conn_info['tabs']['history_widgets'] = {
            'ops_tree': ops_tree,
            'log_text': log_text,
            'refresh_history': refresh_history,
        }

        # Initial load
        refresh_history()

    def _refresh_all_backup_restore_destinations(self):
        """Refresh the destination dropdowns in all open Backup & Restore tabs"""
        for instance_id, conn_info in self.open_connections.items():
            widgets = conn_info['tabs'].get('backup_restore_widgets', {})
            refresh_func = widgets.get('refresh_destinations')
            if refresh_func:
                try:
                    refresh_func()
                except Exception:
                    pass  # Tab might be closing

    def _refresh_all_recent_backups(self):
        """Refresh the Recent Backups list in all open Restore tabs"""
        for instance_id, conn_info in self.open_connections.items():
            widgets = conn_info['tabs'].get('restore_widgets', {})
            refresh_func = widgets.get('refresh_recent')
            if refresh_func:
                try:
                    refresh_func()
                except Exception:
                    pass  # Tab might be closing

    def _new_connection(self):
        """Show dialog to create new connection"""
        dialog = ConnectionDialog(self.root, self.instance_manager,
                                   dark_mode=self.dark_mode_var.get())
        if dialog.result:
            self._refresh_connection_tree()
            self._refresh_all_backup_restore_destinations()

    def _edit_selected(self):
        """Edit the selected connection"""
        instance_id = self._get_selected_instance_id()
        if instance_id is None:
            return

        instance = self.instance_manager.get_instance(instance_id)
        if instance:
            dialog = ConnectionDialog(self.root, self.instance_manager, instance,
                                       dark_mode=self.dark_mode_var.get())
            if dialog.result:
                self._refresh_connection_tree()
                self._refresh_all_backup_restore_destinations()
                # Update open tab if connected
                if instance_id in self.open_connections:
                    # Would need to refresh tab title, etc.
                    pass

    def _delete_selected(self):
        """Delete the selected connection"""
        instance_id = self._get_selected_instance_id()
        if instance_id is None:
            return

        instance = self.instance_manager.get_instance(instance_id)
        if instance is None:
            return

        if messagebox.askyesno("Confirm Delete",
                               f"Delete connection '{instance['name']}'?\n\nThis cannot be undone."):
            # Close if connected
            if instance_id in self.open_connections:
                self._close_connection(instance_id)

            self.instance_manager.delete_instance(instance_id)
            self._refresh_connection_tree()
            self._refresh_all_backup_restore_destinations()

    def _export_connections(self):
        """Export connections to JSON"""
        try:
            json_data = self.instance_manager.export_instances()
            file_path = filedialog.asksaveasfilename(
                title="Export Connections",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json")],
                initialfile="odoobench_connections.json"
            )
            if file_path:
                with open(file_path, 'w') as f:
                    f.write(json_data)
                messagebox.showinfo("Export Complete",
                                    f"Connections exported to:\n{file_path}\n\n"
                                    "Note: Passwords are not exported.")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _import_connections(self):
        """Import connections from JSON"""
        file_path = filedialog.askopenfilename(
            title="Import Connections",
            filetypes=[("JSON files", "*.json")]
        )
        if not file_path:
            return

        try:
            with open(file_path, 'r') as f:
                json_data = f.read()

            success, errors, messages = self.instance_manager.import_instances(json_data)
            self._refresh_connection_tree()
            self._refresh_all_backup_restore_destinations()

            messagebox.showinfo("Import Complete",
                                f"Imported: {success}\nErrors: {errors}\n\n"
                                "Remember to set passwords for imported connections.")
        except Exception as e:
            messagebox.showerror("Import Error", str(e))

    def _toggle_dark_mode(self):
        """Toggle dark mode"""
        is_dark = self.dark_mode_var.get()
        self.instance_manager.set_setting("dark_mode", "1" if is_dark else "0")
        self._apply_theme()

    def _show_settings(self):
        """Show settings dialog"""
        settings_win = tk.Toplevel(self.root)
        settings_win.title("Settings")
        settings_win.transient(self.root)
        settings_win.grab_set()

        # Apply theme to dialog
        is_dark = self.dark_mode_var.get()
        if is_dark:
            settings_win.configure(bg="#2b2b2b")

        main_frame = ttk.Frame(settings_win, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Backup Directory
        backup_frame = ttk.LabelFrame(main_frame, text="Backup Directory", padding=10)
        backup_frame.pack(fill=tk.X, pady=(0, 15))

        backup_dir_var = tk.StringVar(value=self.backup_directory)
        backup_entry = ttk.Entry(backup_frame, textvariable=backup_dir_var, width=40)
        backup_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        def browse_backup_dir():
            path = filedialog.askdirectory(
                title="Select Backup Directory",
                initialdir=backup_dir_var.get()
            )
            if path:
                backup_dir_var.set(path)

        ttk.Button(backup_frame, text="Browse...", command=browse_backup_dir).pack(side=tk.LEFT)

        # Font Size
        font_frame = ttk.LabelFrame(main_frame, text="Font Size", padding=10)
        font_frame.pack(fill=tk.X, pady=(0, 15))

        font_size_var = tk.StringVar(value=str(self.font_size))
        ttk.Label(font_frame, text="Size:").pack(side=tk.LEFT)
        font_spin = ttk.Spinbox(font_frame, from_=8, to=18, width=5,
                                 textvariable=font_size_var)
        font_spin.pack(side=tk.LEFT, padx=(5, 10))
        ttk.Label(font_frame, text="(8-18)").pack(side=tk.LEFT)

        # Dark Mode
        appearance_frame = ttk.LabelFrame(main_frame, text="Appearance", padding=10)
        appearance_frame.pack(fill=tk.X, pady=(0, 15))

        dark_mode_check_var = tk.BooleanVar(value=self.dark_mode_var.get())
        ttk.Checkbutton(appearance_frame, text="Dark Mode",
                        variable=dark_mode_check_var).pack(anchor=tk.W)

        # Import/Export section
        data_frame = ttk.LabelFrame(main_frame, text="Data Management", padding=10)
        data_frame.pack(fill=tk.X, pady=(0, 15))

        btn_row = ttk.Frame(data_frame)
        btn_row.pack(fill=tk.X)

        ttk.Button(btn_row, text="Export Connections...",
                   command=lambda: [settings_win.destroy(), self._export_connections()]).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_row, text="Import Connections...",
                   command=lambda: [settings_win.destroy(), self._import_connections()]).pack(side=tk.LEFT)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        def apply_settings():
            # Validate font size
            try:
                new_font_size = int(font_size_var.get())
                if not 8 <= new_font_size <= 18:
                    messagebox.showwarning("Invalid", "Font size must be between 8 and 18",
                                           parent=settings_win)
                    return
            except ValueError:
                messagebox.showwarning("Invalid", "Please enter a valid font size",
                                       parent=settings_win)
                return

            # Save backup directory
            new_backup_dir = backup_dir_var.get()
            if new_backup_dir != self.backup_directory:
                if not os.path.exists(new_backup_dir):
                    try:
                        os.makedirs(new_backup_dir, exist_ok=True)
                    except Exception as e:
                        messagebox.showerror("Error", f"Cannot create directory:\n{e}",
                                             parent=settings_win)
                        return
                self.backup_directory = new_backup_dir
                self.instance_manager.set_setting("backup_directory", new_backup_dir)

            # Save font size
            if new_font_size != self.font_size:
                self.font_size = new_font_size
                self.instance_manager.set_setting("font_size", str(new_font_size))
                self._apply_font_size()

            # Save dark mode
            if dark_mode_check_var.get() != self.dark_mode_var.get():
                self.dark_mode_var.set(dark_mode_check_var.get())
                self._toggle_dark_mode()

            settings_win.destroy()

        ttk.Button(btn_frame, text="Cancel", command=settings_win.destroy).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="Apply", command=apply_settings).pack(side=tk.RIGHT)

        # Keyboard bindings
        settings_win.bind('<Escape>', lambda e: settings_win.destroy())
        settings_win.bind('<Return>', lambda e: apply_settings())

        # Size and center the dialog after content is created
        settings_win.update_idletasks()
        width = settings_win.winfo_reqwidth() + 40
        height = settings_win.winfo_reqheight() + 20
        x = self.root.winfo_x() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - height) // 2
        settings_win.geometry(f"{width}x{height}+{x}+{y}")
        settings_win.resizable(False, False)

        # Apply theme to the dialog
        self._apply_theme_to_dialog(settings_win)

    def _apply_font_size(self):
        """Apply font size to all UI elements"""
        # Update all named fonts
        for font_name in ["TkDefaultFont", "TkTextFont", "TkMenuFont",
                          "TkHeadingFont", "TkCaptionFont", "TkSmallCaptionFont",
                          "TkIconFont", "TkTooltipFont"]:
            try:
                font = tkfont.nametofont(font_name)
                font.configure(size=self.font_size)
            except Exception:
                pass

        # Update fixed font separately (for logs/code)
        try:
            fixed_font = tkfont.nametofont("TkFixedFont")
            fixed_font.configure(size=self.font_size)
        except Exception:
            pass

        # Update ttk style for Treeview row height
        style = ttk.Style()
        rowheight = int(self.font_size * 1.8)
        style.configure("Treeview", rowheight=rowheight)

    def _apply_theme(self):
        """Apply light or dark theme"""
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
            style.configure("TScrollbar", background="#4a4a4a", troughcolor=bg_dark,
                           arrowcolor=fg)
            style.configure("Treeview", background=bg_light, foreground=fg, fieldbackground=bg_light)
            style.configure("Treeview.Heading", background=bg, foreground=fg)
            style.configure("TCheckbutton", background=bg, foreground=fg)
            style.configure("TSpinbox", fieldbackground=bg_light, foreground=fg)

            style.map("TButton", background=[("active", bg_light)])
            style.map("TNotebook.Tab", background=[("selected", bg), ("active", bg_light)])
            style.map("Treeview", background=[("selected", select_bg)], foreground=[("selected", fg)])
            style.map("TCombobox", fieldbackground=[("readonly", bg_light)])
            style.map("TCheckbutton", background=[("active", bg)])

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
            style.configure("TSpinbox", fieldbackground=bg_light, foreground=fg)

            style.map("TButton", background=[("active", "#ececec")])
            style.map("TNotebook.Tab", background=[("selected", bg)])
            style.map("Treeview", background=[("selected", select_bg)], foreground=[("selected", "#ffffff")])
            style.map("TCombobox", fieldbackground=[("readonly", bg_light)])
            style.map("TCheckbutton", background=[("active", bg)])

            self.root.configure(bg=bg)

        # Apply to non-ttk widgets
        self._apply_theme_to_widgets()

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
            elif widget_class == "Toplevel":
                widget.configure(bg=menu_bg)
        except tk.TclError:
            pass

        for child in widget.winfo_children():
            self._configure_widgets_recursive(child, bg, fg, select_bg, menu_bg)

    def _apply_theme_to_dialog(self, dialog):
        """Apply current theme to a dialog window."""
        is_dark = self.dark_mode_var.get()

        if is_dark:
            bg = "#2b2b2b"
            fg = "#a9b7c6"
            text_bg = "#313335"
            select_bg = "#214283"
            dialog.configure(bg=bg)
            self._configure_widgets_recursive(dialog, text_bg, fg, select_bg, bg)

    def _show_about(self):
        """Show about dialog"""
        messagebox.showinfo("About OdooBench",
                            f"OdooBench v{__version__}\n\n"
                            "Odoo Instance Manager\n"
                            "Backup, Restore & Administration Tool\n\n"
                            "https://github.com/jpsteil/odoobench")

    # -------------------------------------------------------------------------
    # Window geometry and state persistence
    # -------------------------------------------------------------------------

    def _on_configure(self, event):
        """Handle window configure events (resize/move) - debounced save."""
        # Only save when it's the root window being configured
        if event.widget == self.root:
            # Debounce: cancel previous pending save and schedule a new one
            if self._geometry_save_pending:
                self.root.after_cancel(self._geometry_save_pending)
            # Save after 500ms of no resize/move activity
            self._geometry_save_pending = self.root.after(500, self._save_geometry_debounced)

    def _save_geometry_debounced(self):
        """Save geometry after debounce period."""
        self._geometry_save_pending = False
        self._save_geometry()
        self._save_layout()

    def _start_autosave(self):
        """Start periodic autosave of window state."""
        def autosave():
            try:
                self._save_geometry()
                self._save_layout()
                self._save_active_tab()
                self._save_open_connections()
            except Exception:
                pass  # Silently ignore errors during autosave
            # Schedule next autosave in 30 seconds
            self.root.after(30000, autosave)

        # Start first autosave after 10 seconds
        self.root.after(10000, autosave)

    def _restore_geometry(self):
        """Restore window geometry from saved settings."""
        default_geometry = "1200x700"
        saved = self.instance_manager.get_setting("window_geometry", default_geometry)

        try:
            self.root.geometry(saved)
            self.root.update_idletasks()

            # Make sure window is visible on screen
            if not self._is_visible_on_screen():
                self.root.geometry(default_geometry)
                self._center_window()
        except Exception:
            self.root.geometry(default_geometry)

    def _is_visible_on_screen(self):
        """Check if at least part of the window is visible on screen."""
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        w = self.root.winfo_width()
        h = self.root.winfo_height()

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        min_visible = 100
        visible_x = x + w > min_visible and x < screen_w - min_visible
        visible_y = y + h > min_visible and y < screen_h - min_visible

        return visible_x and visible_y

    def _center_window(self):
        """Center window on screen."""
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - w) // 2
        y = (screen_h - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _save_geometry(self):
        """Save current window geometry."""
        try:
            geometry = self.root.geometry()
            self.instance_manager.set_setting("window_geometry", geometry)
        except Exception:
            pass

    def _restore_layout(self):
        """Restore paned window sash positions."""
        try:
            # Main paned window (connections | tabs)
            sash_pos = self.instance_manager.get_setting("layout_main_sash")
            if sash_pos:
                self.main_paned.sashpos(0, int(sash_pos))
        except Exception:
            pass

    def _save_layout(self):
        """Save paned window sash positions."""
        try:
            sash_pos = self.main_paned.sashpos(0)
            self.instance_manager.set_setting("layout_main_sash", str(sash_pos))
        except Exception:
            pass

    def _save_active_tab(self):
        """Save the currently active connection tab index."""
        try:
            current_tab = self.connection_notebook.select()
            if current_tab:
                tabs = self.connection_notebook.tabs()
                for idx, tab_id in enumerate(tabs):
                    if tab_id == current_tab:
                        self.instance_manager.set_setting("last_active_tab", str(idx))
                        return
        except Exception:
            pass

    def _restore_active_tab(self):
        """Restore the last active connection tab."""
        try:
            last_tab_idx = self.instance_manager.get_setting("last_active_tab")
            if last_tab_idx is not None:
                idx = int(last_tab_idx)
                tabs = self.connection_notebook.tabs()
                if 0 <= idx < len(tabs):
                    self.connection_notebook.select(tabs[idx])
        except Exception:
            pass

    def _save_open_connections(self):
        """Save list of open connection IDs and their active feature tabs."""
        try:
            import json
            # Save connection IDs along with their active feature tab index
            connection_state = {}
            for instance_id, conn_info in self.open_connections.items():
                feature_tab_idx = 0
                try:
                    feature_notebook = conn_info.get('feature_notebook')
                    if feature_notebook:
                        current = feature_notebook.select()
                        if current:
                            tabs = feature_notebook.tabs()
                            feature_tab_idx = tabs.index(current) if current in tabs else 0
                except Exception:
                    pass
                connection_state[str(instance_id)] = {'feature_tab': feature_tab_idx}

            self.instance_manager.set_setting("open_connections", json.dumps(connection_state))
        except Exception:
            pass

    def _restore_open_connections(self):
        """Restore previously open connections and their feature tabs."""
        try:
            import json
            saved = self.instance_manager.get_setting("open_connections")
            if saved:
                connection_state = json.loads(saved)
                # Handle old format (list of IDs) and new format (dict with state)
                if isinstance(connection_state, list):
                    # Old format - just IDs
                    for instance_id in connection_state:
                        instance = self.instance_manager.get_instance(instance_id)
                        if instance:
                            self._open_connection(instance)
                else:
                    # New format - dict with state
                    for instance_id_str, state in connection_state.items():
                        instance_id = int(instance_id_str)
                        instance = self.instance_manager.get_instance(instance_id)
                        if instance:
                            self._open_connection(instance)
                            # Restore feature tab after a delay
                            feature_tab_idx = state.get('feature_tab', 0)
                            if feature_tab_idx > 0:
                                self.root.after(300, lambda iid=instance_id, idx=feature_tab_idx:
                                               self._restore_feature_tab(iid, idx))

                # Restore active connection tab after opening all connections
                self._restore_active_tab()
        except Exception:
            pass

    def _restore_feature_tab(self, instance_id: int, tab_idx: int):
        """Restore the active feature tab for a connection."""
        try:
            if instance_id in self.open_connections:
                feature_notebook = self.open_connections[instance_id].get('feature_notebook')
                if feature_notebook:
                    tabs = feature_notebook.tabs()
                    if 0 <= tab_idx < len(tabs):
                        feature_notebook.select(tabs[tab_idx])
        except Exception:
            pass

    def _on_close(self):
        """Handle window close event - save all state."""
        self._save_geometry()
        self._save_layout()
        self._save_active_tab()
        self._save_open_connections()

        # Disconnect all open connections
        for instance_id in list(self.open_connections.keys()):
            try:
                self.open_connections[instance_id]['executor'].disconnect()
            except Exception:
                pass

        self.root.destroy()


class ConnectionDialog:
    """Dialog for creating/editing Odoo instance connections"""

    def __init__(self, parent, instance_manager: OdooInstanceManager,
                 existing: Dict[str, Any] = None, dark_mode: bool = False):
        self.parent = parent
        self.instance_manager = instance_manager
        self.existing = existing
        self.dark_mode = dark_mode
        self.result = False

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Edit Connection" if existing else "New Connection")
        self.dialog.geometry("550x650")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self._create_widgets()

        if existing:
            self._populate_fields()

        # Center on parent
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")

        # Apply dark mode theme if needed
        if self.dark_mode:
            self._apply_dark_theme()

        self.dialog.wait_window()

    def _apply_dark_theme(self):
        """Apply dark theme to dialog"""
        bg = "#2b2b2b"
        fg = "#a9b7c6"
        text_bg = "#313335"
        select_bg = "#214283"

        self.dialog.configure(bg=bg)
        self._configure_widgets_recursive(self.dialog, text_bg, fg, select_bg, bg)

    def _configure_widgets_recursive(self, widget, bg, fg, select_bg, menu_bg):
        """Recursively configure non-ttk widgets for dark mode."""
        widget_class = widget.winfo_class()

        try:
            if widget_class == "Text":
                widget.configure(bg=bg, fg=fg, insertbackground=fg,
                               selectbackground=select_bg, selectforeground=fg)
            elif widget_class == "Listbox":
                widget.configure(bg=bg, fg=fg,
                               selectbackground=select_bg, selectforeground=fg)
            elif widget_class == "Canvas":
                widget.configure(bg=menu_bg)
            elif widget_class == "Toplevel":
                widget.configure(bg=menu_bg)
        except tk.TclError:
            pass

        for child in widget.winfo_children():
            self._configure_widgets_recursive(child, bg, fg, select_bg, menu_bg)

    def _create_widgets(self):
        """Create dialog widgets"""
        # Main frame with scrollbar
        self.canvas = tk.Canvas(self.dialog)
        scrollbar = ttk.Scrollbar(self.dialog, orient=tk.VERTICAL, command=self.canvas.yview)
        main_frame = ttk.Frame(self.canvas)

        main_frame.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.create_window((0, 0), window=main_frame, anchor=tk.NW)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Mouse wheel scrolling support
        def _on_mousewheel(event):
            # Windows and MacOS use event.delta, Linux uses event.num
            if event.delta:
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            elif event.num == 4:
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self.canvas.yview_scroll(1, "units")

        # Bind mouse wheel to canvas and dialog
        self.canvas.bind_all("<MouseWheel>", _on_mousewheel)  # Windows/MacOS
        self.canvas.bind_all("<Button-4>", _on_mousewheel)    # Linux scroll up
        self.canvas.bind_all("<Button-5>", _on_mousewheel)    # Linux scroll down

        # Store reference for cleanup
        self._mousewheel_handler = _on_mousewheel

        # Cleanup bindings when dialog closes
        def _cleanup(event):
            try:
                self.canvas.unbind_all("<MouseWheel>")
                self.canvas.unbind_all("<Button-4>")
                self.canvas.unbind_all("<Button-5>")
            except tk.TclError:
                pass

        self.dialog.bind("<Destroy>", _cleanup)

        # Name
        name_frame = ttk.LabelFrame(main_frame, text="Connection Name", padding=10)
        name_frame.pack(fill=tk.X, padx=10, pady=5)

        self.name_var = tk.StringVar()
        ttk.Entry(name_frame, textvariable=self.name_var, width=40).pack(fill=tk.X)

        # SSH/Host settings
        ssh_frame = ttk.LabelFrame(main_frame, text="Host / SSH Connection", padding=10)
        ssh_frame.pack(fill=tk.X, padx=10, pady=5)

        self.is_local_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ssh_frame, text="Local (this machine)",
                        variable=self.is_local_var,
                        command=self._toggle_ssh_fields).pack(anchor=tk.W)

        ssh_grid = ttk.Frame(ssh_frame)
        ssh_grid.pack(fill=tk.X, pady=5)

        row = 0
        ttk.Label(ssh_grid, text="Host:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.host_var = tk.StringVar(value="localhost")
        self.host_entry = ttk.Entry(ssh_grid, textvariable=self.host_var, width=30)
        self.host_entry.grid(row=row, column=1, sticky=tk.W, pady=2)

        row += 1
        ttk.Label(ssh_grid, text="SSH Port:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.ssh_port_var = tk.StringVar(value="22")
        self.ssh_port_entry = ttk.Entry(ssh_grid, textvariable=self.ssh_port_var, width=10)
        self.ssh_port_entry.grid(row=row, column=1, sticky=tk.W, pady=2)

        row += 1
        ttk.Label(ssh_grid, text="Username:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.ssh_user_var = tk.StringVar()
        self.ssh_user_entry = ttk.Entry(ssh_grid, textvariable=self.ssh_user_var, width=20)
        self.ssh_user_entry.grid(row=row, column=1, sticky=tk.W, pady=2)

        row += 1
        ttk.Label(ssh_grid, text="Password:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.ssh_pass_var = tk.StringVar()
        self.ssh_pass_entry = ttk.Entry(ssh_grid, textvariable=self.ssh_pass_var, width=20, show="*")
        self.ssh_pass_entry.grid(row=row, column=1, sticky=tk.W, pady=2)

        row += 1
        ttk.Label(ssh_grid, text="Key file:").grid(row=row, column=0, sticky=tk.W, pady=2)
        key_frame = ttk.Frame(ssh_grid)
        key_frame.grid(row=row, column=1, sticky=tk.W, pady=2)
        self.ssh_key_var = tk.StringVar()
        self.ssh_key_entry = ttk.Entry(key_frame, textvariable=self.ssh_key_var, width=25)
        self.ssh_key_entry.pack(side=tk.LEFT)
        ttk.Button(key_frame, text="...", width=3,
                   command=self._browse_key_file).pack(side=tk.LEFT, padx=2)

        # Odoo paths
        odoo_frame = ttk.LabelFrame(main_frame, text="Odoo Configuration", padding=10)
        odoo_frame.pack(fill=tk.X, padx=10, pady=5)

        row = 0
        ttk.Label(odoo_frame, text="odoo.conf path:").grid(row=row, column=0, sticky=tk.W, pady=2)
        conf_entry_frame = ttk.Frame(odoo_frame)
        conf_entry_frame.grid(row=row, column=1, sticky=tk.W, pady=2)
        self.conf_path_var = tk.StringVar(value="/etc/odoo/odoo.conf")
        ttk.Entry(conf_entry_frame, textvariable=self.conf_path_var, width=35).pack(side=tk.LEFT)
        self.conf_browse_btn = ttk.Button(conf_entry_frame, text="...", width=3,
                                           command=self._browse_conf_file)
        self.conf_browse_btn.pack(side=tk.LEFT, padx=2)

        row += 1
        ttk.Label(odoo_frame, text="Log file:").grid(row=row, column=0, sticky=tk.W, pady=2)
        log_entry_frame = ttk.Frame(odoo_frame)
        log_entry_frame.grid(row=row, column=1, sticky=tk.W, pady=2)
        self.log_path_var = tk.StringVar(value="/var/log/odoo/odoo-server.log")
        ttk.Entry(log_entry_frame, textvariable=self.log_path_var, width=35).pack(side=tk.LEFT)
        self.log_browse_btn = ttk.Button(log_entry_frame, text="...", width=3,
                                          command=self._browse_log_file)
        self.log_browse_btn.pack(side=tk.LEFT, padx=2)

        row += 1
        ttk.Label(odoo_frame, text="Filestore path:").grid(row=row, column=0, sticky=tk.W, pady=2)
        fs_entry_frame = ttk.Frame(odoo_frame)
        fs_entry_frame.grid(row=row, column=1, sticky=tk.W, pady=2)
        self.filestore_var = tk.StringVar(value="/var/lib/odoo")
        ttk.Entry(fs_entry_frame, textvariable=self.filestore_var, width=35).pack(side=tk.LEFT)
        self.fs_browse_btn = ttk.Button(fs_entry_frame, text="...", width=3,
                                         command=self._browse_filestore)
        self.fs_browse_btn.pack(side=tk.LEFT, padx=2)

        row += 1
        ttk.Button(odoo_frame, text="Auto-Discover from odoo.conf",
                   command=self._auto_discover).grid(row=row, column=0, columnspan=2, pady=10)

        # Database settings
        db_frame = ttk.LabelFrame(main_frame, text="Database Connection", padding=10)
        db_frame.pack(fill=tk.X, padx=10, pady=5)

        row = 0
        ttk.Label(db_frame, text="DB Host:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.db_host_var = tk.StringVar(value="localhost")
        ttk.Entry(db_frame, textvariable=self.db_host_var, width=20).grid(row=row, column=1, sticky=tk.W, pady=2)

        row += 1
        ttk.Label(db_frame, text="DB Port:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.db_port_var = tk.StringVar(value="5432")
        ttk.Entry(db_frame, textvariable=self.db_port_var, width=10).grid(row=row, column=1, sticky=tk.W, pady=2)

        row += 1
        ttk.Label(db_frame, text="DB User:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.db_user_var = tk.StringVar(value="odoo")
        ttk.Entry(db_frame, textvariable=self.db_user_var, width=20).grid(row=row, column=1, sticky=tk.W, pady=2)

        row += 1
        ttk.Label(db_frame, text="DB Password:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.db_pass_var = tk.StringVar()
        ttk.Entry(db_frame, textvariable=self.db_pass_var, width=20, show="*").grid(row=row, column=1, sticky=tk.W, pady=2)

        row += 1
        ttk.Label(db_frame, text="Database:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.db_name_var = tk.StringVar()
        ttk.Entry(db_frame, textvariable=self.db_name_var, width=20).grid(row=row, column=1, sticky=tk.W, pady=2)

        # Options
        options_frame = ttk.LabelFrame(main_frame, text="Options", padding=10)
        options_frame.pack(fill=tk.X, padx=10, pady=5)

        self.is_production_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Production instance (show warnings)",
                        variable=self.is_production_var).pack(anchor=tk.W)

        self.allow_restore_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Allow restore to this instance",
                        variable=self.allow_restore_var).pack(anchor=tk.W)

        ttk.Label(options_frame, text="Group:").pack(anchor=tk.W, pady=(10, 0))
        self.group_var = tk.StringVar()
        group_combo = ttk.Combobox(options_frame, textvariable=self.group_var, width=20)
        group_combo['values'] = self.instance_manager.get_groups() + ['Production', 'Staging', 'Development', 'Local']
        group_combo.pack(anchor=tk.W)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, padx=10, pady=20)

        ttk.Button(btn_frame, text="Cancel", command=self.dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Save", command=self._save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Test Connection", command=self._test_connection).pack(side=tk.LEFT, padx=5)

        # Initial state
        self._toggle_ssh_fields()

    def _toggle_ssh_fields(self):
        """Enable/disable SSH fields based on local checkbox"""
        is_local = self.is_local_var.get()
        state = 'disabled' if is_local else 'normal'

        self.host_entry.configure(state=state)
        self.ssh_port_entry.configure(state=state)
        self.ssh_user_entry.configure(state=state)
        self.ssh_pass_entry.configure(state=state)
        self.ssh_key_entry.configure(state=state)

        # Show/hide browse buttons for paths (only useful for local connections)
        browse_state = 'normal' if is_local else 'disabled'
        self.conf_browse_btn.configure(state=browse_state)
        self.log_browse_btn.configure(state=browse_state)
        self.fs_browse_btn.configure(state=browse_state)

    def _browse_key_file(self):
        """Browse for SSH key file"""
        path = filedialog.askopenfilename(
            title="Select SSH Key",
            initialdir=os.path.expanduser("~/.ssh"),
            filetypes=[("All files", "*")],
            parent=self.dialog
        )
        if path:
            self.ssh_key_var.set(path)

    def _browse_conf_file(self):
        """Browse for odoo.conf file (local connections only)"""
        initial_dir = "/etc/odoo" if os.path.exists("/etc/odoo") else os.path.expanduser("~")
        path = filedialog.askopenfilename(
            title="Select odoo.conf",
            initialdir=initial_dir,
            filetypes=[("Config files", "*.conf"), ("All files", "*")],
            parent=self.dialog
        )
        if path:
            self.conf_path_var.set(path)

    def _browse_log_file(self):
        """Browse for log file (local connections only)"""
        initial_dir = "/var/log/odoo" if os.path.exists("/var/log/odoo") else os.path.expanduser("~")
        path = filedialog.askopenfilename(
            title="Select Log File",
            initialdir=initial_dir,
            filetypes=[("Log files", "*.log"), ("All files", "*")],
            parent=self.dialog
        )
        if path:
            self.log_path_var.set(path)

    def _browse_filestore(self):
        """Browse for filestore directory (local connections only)"""
        initial_dir = "/var/lib/odoo" if os.path.exists("/var/lib/odoo") else os.path.expanduser("~")
        path = filedialog.askdirectory(
            title="Select Filestore Directory",
            initialdir=initial_dir,
            parent=self.dialog
        )
        if path:
            self.filestore_var.set(path)

    def _auto_discover(self):
        """Auto-discover settings from odoo.conf"""
        conf_path = self.conf_path_var.get()
        if not conf_path:
            messagebox.showwarning("Warning", "Please specify odoo.conf path first",
                                   parent=self.dialog)
            return

        try:
            # Create executor based on current settings
            if self.is_local_var.get():
                exec_config = {'is_local': True}
            else:
                exec_config = {
                    'host': self.host_var.get(),
                    'port': int(self.ssh_port_var.get() or 22),
                    'username': self.ssh_user_var.get(),
                    'password': self.ssh_pass_var.get(),
                    'key_path': self.ssh_key_var.get(),
                }

            executor = create_executor(exec_config)
            parser = OdooConfigParser(executor)

            config = parser.discover_all(conf_path)

            # Populate fields
            if config.get('log_path'):
                self.log_path_var.set(config['log_path'])
            if config.get('filestore_path'):
                self.filestore_var.set(config['filestore_path'])
            if config.get('db_host'):
                self.db_host_var.set(config['db_host'])
            if config.get('db_port'):
                self.db_port_var.set(str(config['db_port']))
            if config.get('db_user'):
                self.db_user_var.set(config['db_user'])
            if config.get('db_password'):
                self.db_pass_var.set(config['db_password'])
            if config.get('db_name'):
                self.db_name_var.set(config['db_name'])

            executor.disconnect()
            messagebox.showinfo("Success", "Settings discovered from odoo.conf",
                               parent=self.dialog)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to discover settings:\n{e}",
                                parent=self.dialog)

    def _test_connection(self):
        """Test the connection"""
        try:
            if self.is_local_var.get():
                exec_config = {'is_local': True}
            else:
                exec_config = {
                    'host': self.host_var.get(),
                    'port': int(self.ssh_port_var.get() or 22),
                    'username': self.ssh_user_var.get(),
                    'password': self.ssh_pass_var.get(),
                    'key_path': self.ssh_key_var.get(),
                }

            executor = create_executor(exec_config)

            # Test basic connectivity
            stdout, stderr, code = executor.run_command("echo 'Connection successful'")
            executor.disconnect()

            if code == 0:
                messagebox.showinfo("Success", "Connection test successful!",
                                   parent=self.dialog)
            else:
                messagebox.showerror("Error", f"Connection test failed:\n{stderr}",
                                    parent=self.dialog)

        except Exception as e:
            messagebox.showerror("Error", f"Connection test failed:\n{e}",
                                parent=self.dialog)

    def _populate_fields(self):
        """Populate fields from existing connection"""
        e = self.existing

        self.name_var.set(e.get('name', ''))
        self.is_local_var.set(e.get('is_local', True))
        self.host_var.set(e.get('host', 'localhost'))
        self.ssh_port_var.set(str(e.get('ssh_port', 22)))
        self.ssh_user_var.set(e.get('ssh_username', ''))
        self.ssh_pass_var.set(e.get('ssh_password', ''))
        self.ssh_key_var.set(e.get('ssh_key_path', ''))
        self.conf_path_var.set(e.get('odoo_conf_path', '/etc/odoo/odoo.conf'))
        self.log_path_var.set(e.get('log_path', ''))
        self.filestore_var.set(e.get('filestore_path', ''))
        self.db_host_var.set(e.get('db_host', 'localhost'))
        self.db_port_var.set(str(e.get('db_port', 5432)))
        self.db_user_var.set(e.get('db_user', 'odoo'))
        self.db_pass_var.set(e.get('db_password', ''))
        self.db_name_var.set(e.get('db_name', ''))
        self.is_production_var.set(e.get('is_production', False))
        self.allow_restore_var.set(e.get('allow_restore', False))
        self.group_var.set(e.get('group_name', ''))

        self._toggle_ssh_fields()

    def _save(self):
        """Save the connection"""
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Warning", "Please enter a connection name",
                                   parent=self.dialog)
            return

        config = {
            'host': self.host_var.get() or 'localhost',
            'ssh_port': int(self.ssh_port_var.get() or 22),
            'ssh_username': self.ssh_user_var.get() if not self.is_local_var.get() else None,
            'ssh_password': self.ssh_pass_var.get() if not self.is_local_var.get() else None,
            'ssh_key_path': self.ssh_key_var.get() if not self.is_local_var.get() else None,
            'is_local': self.is_local_var.get(),
            'odoo_conf_path': self.conf_path_var.get(),
            'log_path': self.log_path_var.get(),
            'filestore_path': self.filestore_var.get(),
            'db_host': self.db_host_var.get() or 'localhost',
            'db_port': int(self.db_port_var.get() or 5432),
            'db_user': self.db_user_var.get() or 'odoo',
            'db_password': self.db_pass_var.get(),
            'db_name': self.db_name_var.get(),
            'is_production': self.is_production_var.get(),
            'allow_restore': self.allow_restore_var.get(),
            'group_name': self.group_var.get(),
        }

        try:
            if self.existing:
                self.instance_manager.update_instance(self.existing['id'], name, config)
            else:
                self.instance_manager.save_instance(name, config)

            self.result = True
            self.dialog.destroy()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to save connection:\n{e}")


def launch_instance_window():
    """Launch the instance manager window"""
    root = tk.Tk()
    app = InstanceWindow(root)
    root.mainloop()


if __name__ == "__main__":
    launch_instance_window()
