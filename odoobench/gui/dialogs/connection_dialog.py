"""Unified connection dialog for adding/editing Odoo and SSH connections"""

import tkinter as tk
from tkinter import ttk, messagebox
import json


class ConnectionDialog(tk.Toplevel):
    """Base dialog for managing connections (Odoo and SSH)"""
    
    def __init__(self, parent, title, connection_type="odoo", connection_data=None):
        """
        Initialize connection dialog
        
        Args:
            parent: Parent window
            title: Dialog title
            connection_type: "odoo" or "ssh"
            connection_data: Existing connection data for editing (None for new)
        """
        super().__init__(parent)
        self.parent = parent
        self.title(title)
        self.connection_type = connection_type
        self.connection_data = connection_data
        self.is_edit = connection_data is not None
        self.result = None
        
        # Make dialog modal
        self.transient(parent)
        self.grab_set()
        
        # Configure dialog
        self.resizable(False, False)
        
        # Create interface
        self.create_widgets()
        
        # Load existing data if editing
        if self.is_edit:
            self.load_connection_data()
        
        # Center dialog
        self.center_window()
        
        # Focus on first entry
        if self.connection_type == "odoo":
            self.name_entry.focus_set()
        else:
            self.ssh_name_entry.focus_set()
    
    def center_window(self):
        """Center dialog on parent window"""
        self.update_idletasks()
        
        # Get parent position and size
        parent_x = self.parent.winfo_x()
        parent_y = self.parent.winfo_y()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()
        
        # Get dialog size
        dialog_width = self.winfo_width()
        dialog_height = self.winfo_height()
        
        # Calculate position - center on parent
        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2
        
        # Get screen dimensions
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # For multi-monitor setups, ensure dialog stays on the same monitor as parent
        # Check if we're likely in a multi-monitor setup (width > 2x height suggests side-by-side)
        if screen_width > screen_height * 2:
            # Likely multi-monitor side-by-side
            primary_width = screen_width // 2
            
            # Determine which monitor the parent is on
            parent_center_x = parent_x + parent_width // 2
            
            if parent_center_x < primary_width:
                # Parent is on left (primary) monitor
                # Ensure dialog doesn't go past right edge of primary monitor
                x = min(x, primary_width - dialog_width - 10)
                x = max(10, x)  # At least 10px from left edge
            else:
                # Parent is on right (secondary) monitor
                # Ensure dialog stays on right monitor
                x = max(x, primary_width + 10)
                x = min(x, screen_width - dialog_width - 10)
        else:
            # Single monitor or vertical setup
            # Just ensure we don't go off screen
            x = max(10, min(x, screen_width - dialog_width - 10))
        
        # Ensure vertical position is reasonable
        y = max(10, min(y, screen_height - dialog_height - 10))
        
        self.geometry(f"+{x}+{y}")
    
    def create_widgets(self):
        """Create dialog widgets based on connection type"""
        if self.connection_type == "odoo":
            self.create_odoo_widgets()
        else:
            self.create_ssh_widgets()
    
    def create_odoo_widgets(self):
        """Create widgets for Odoo connection"""
        # Main frame
        main_frame = ttk.Frame(self, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Load button at top
        ttk.Button(
            main_frame,
            text="Load from odoo.conf",
            command=lambda: self.load_from_odoo_conf(),
        ).pack(pady=(0, 15))
        
        # Connection Details Frame
        details_frame = ttk.LabelFrame(main_frame, text="Connection Details", padding="10")
        details_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Connection name
        row = 0
        ttk.Label(details_frame, text="Connection Name:").grid(
            row=row, column=0, sticky="e", padx=(0, 10), pady=5
        )
        self.name_entry = ttk.Entry(details_frame, width=30)
        self.name_entry.grid(row=row, column=1, sticky="ew", pady=5)
        row += 1
        
        # Host
        ttk.Label(details_frame, text="Host:").grid(
            row=row, column=0, sticky="e", padx=(0, 10), pady=5
        )
        self.host_entry = ttk.Entry(details_frame, width=30)
        self.host_entry.grid(row=row, column=1, sticky="ew", pady=5)
        row += 1
        
        # Port
        ttk.Label(details_frame, text="Port:").grid(
            row=row, column=0, sticky="e", padx=(0, 10), pady=5
        )
        self.port_entry = ttk.Entry(details_frame, width=30)
        self.port_entry.insert(0, "5432")
        self.port_entry.grid(row=row, column=1, sticky="ew", pady=5)
        row += 1
        
        # Database
        ttk.Label(details_frame, text="Database:").grid(
            row=row, column=0, sticky="e", padx=(0, 10), pady=5
        )
        self.database_entry = ttk.Entry(details_frame, width=30)
        self.database_entry.grid(row=row, column=1, sticky="ew", pady=5)
        row += 1
        
        # Username
        ttk.Label(details_frame, text="Username:").grid(
            row=row, column=0, sticky="e", padx=(0, 10), pady=5
        )
        self.username_entry = ttk.Entry(details_frame, width=30)
        self.username_entry.grid(row=row, column=1, sticky="ew", pady=5)
        row += 1
        
        # Password
        ttk.Label(details_frame, text="Password:").grid(
            row=row, column=0, sticky="e", padx=(0, 10), pady=5
        )
        self.password_entry = ttk.Entry(details_frame, width=30, show="*")
        self.password_entry.grid(row=row, column=1, sticky="ew", pady=5)
        row += 1
        
        # Filestore path with Browse button
        ttk.Label(details_frame, text="Filestore Path:").grid(
            row=row, column=0, sticky="e", padx=(0, 10), pady=5
        )
        path_frame = ttk.Frame(details_frame)
        path_frame.grid(row=row, column=1, sticky="ew", pady=5)
        self.filestore_entry = ttk.Entry(path_frame, width=22)
        self.filestore_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.browse_button = ttk.Button(
            path_frame,
            text="Browse",
            command=lambda: self.browse_folder(),
            width=8
        )
        self.browse_button.pack(side=tk.LEFT, padx=(5, 0))
        row += 1
        
        # Odoo Version
        ttk.Label(details_frame, text="Odoo Version:").grid(
            row=row, column=0, sticky="e", padx=(0, 10), pady=5
        )
        self.odoo_version_combo = ttk.Combobox(
            details_frame, width=28, 
            values=["18.0", "17.0", "16.0", "15.0", "14.0", "13.0", "12.0"],
            state="readonly"
        )
        self.odoo_version_combo.grid(row=row, column=1, sticky="ew", pady=5)
        self.odoo_version_combo.set("17.0")
        row += 1
        
        # Local Development checkbox
        self.is_local_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            details_frame, text="Local Development Connection", 
            variable=self.is_local_var
        ).grid(row=row, column=1, sticky="w", pady=5)
        row += 1
        
        # Allow restore checkbox
        self.allow_restore_var = tk.BooleanVar(value=False)
        allow_restore_check = ttk.Checkbutton(
            details_frame, 
            text="Allow Restore Operations (⚠️ Be careful with production databases!)",
            variable=self.allow_restore_var
        )
        allow_restore_check.grid(row=row, column=1, sticky="w", pady=5)
        
        # Configure column to expand
        details_frame.columnconfigure(1, weight=1)
        
        # SSH Options Frame
        ssh_frame = ttk.LabelFrame(main_frame, text="Remote Server Access", padding="10")
        ssh_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Use SSH checkbox
        self.use_ssh_var = tk.BooleanVar(value=False)
        self.use_ssh_check = ttk.Checkbutton(
            ssh_frame, 
            text="Use SSH connection for remote server access",
            variable=self.use_ssh_var,
            command=self.toggle_ssh_controls
        )
        self.use_ssh_check.pack(anchor="w", pady=(0, 5))
        
        # SSH Connection Dropdown
        ssh_select_frame = ttk.Frame(ssh_frame)
        ssh_select_frame.pack(fill=tk.X)
        
        ttk.Label(ssh_select_frame, text="SSH Connection:").pack(side=tk.LEFT, padx=(20, 10))
        
        # Get list of SSH connections and create mapping
        self.ssh_connections = []
        self.ssh_connection_map = {}  # Map names to IDs
        
        if hasattr(self.parent, 'conn_manager'):
            all_connections = self.parent.conn_manager.list_connections()
            for conn in all_connections:
                if conn['type'] == "ssh":
                    self.ssh_connections.append(conn['name'])
                    self.ssh_connection_map[conn['name']] = conn['id']
        
        self.ssh_combo = ttk.Combobox(
            ssh_select_frame, width=30, 
            values=self.ssh_connections, 
            state="disabled"
        )
        self.ssh_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if self.ssh_connections:
            self.ssh_combo.set(self.ssh_connections[0])
        
        # Button frame at bottom
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Center the buttons
        ttk.Button(button_frame, text="Test Connection", 
                  command=self.test_connection).pack(side=tk.LEFT, padx=5)
        
        save_text = "Update" if self.is_edit else "Save"
        ttk.Button(
            button_frame, text=save_text, command=self.save_odoo_connection
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame, text="Cancel", command=self.destroy
        ).pack(side=tk.LEFT, padx=5)
    
    def create_ssh_widgets(self):
        """Create widgets for SSH connection"""
        # Main frame
        main_frame = ttk.Frame(self, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Connection name
        tk.Label(main_frame, text="Connection Name:").grid(
            row=0, column=0, sticky="e", padx=5, pady=5
        )
        self.ssh_name_entry = tk.Entry(main_frame, width=40)
        self.ssh_name_entry.grid(row=0, column=1, padx=5, pady=5)
        
        # Host
        tk.Label(main_frame, text="Host:").grid(
            row=1, column=0, sticky="e", padx=5, pady=5
        )
        self.ssh_host_entry = tk.Entry(main_frame, width=40)
        self.ssh_host_entry.grid(row=1, column=1, padx=5, pady=5)
        
        # Port
        tk.Label(main_frame, text="Port:").grid(
            row=2, column=0, sticky="e", padx=5, pady=5
        )
        self.ssh_port_entry = tk.Entry(main_frame, width=40)
        self.ssh_port_entry.insert(0, "22")
        self.ssh_port_entry.grid(row=2, column=1, padx=5, pady=5)
        
        # Username
        tk.Label(main_frame, text="Username:").grid(
            row=3, column=0, sticky="e", padx=5, pady=5
        )
        self.ssh_username_entry = tk.Entry(main_frame, width=40)
        self.ssh_username_entry.grid(row=3, column=1, padx=5, pady=5)
        
        # Authentication method
        tk.Label(main_frame, text="Authentication:").grid(
            row=4, column=0, sticky="e", padx=5, pady=5
        )
        
        auth_frame = tk.Frame(main_frame)
        auth_frame.grid(row=4, column=1, sticky="w", padx=5, pady=5)
        
        self.ssh_auth_var = tk.StringVar(value="password")
        tk.Radiobutton(
            auth_frame, text="Password", variable=self.ssh_auth_var,
            value="password", command=self.toggle_ssh_auth
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Radiobutton(
            auth_frame, text="SSH Key", variable=self.ssh_auth_var,
            value="key", command=self.toggle_ssh_auth
        ).pack(side=tk.LEFT, padx=5)
        
        # Password
        self.ssh_password_label = tk.Label(main_frame, text="Password:")
        self.ssh_password_label.grid(row=5, column=0, sticky="e", padx=5, pady=5)
        self.ssh_password_entry = tk.Entry(main_frame, width=40, show="*")
        self.ssh_password_entry.grid(row=5, column=1, padx=5, pady=5)
        
        # SSH Key path
        self.ssh_key_label = tk.Label(main_frame, text="SSH Key Path:")
        self.ssh_key_entry = tk.Entry(main_frame, width=40)
        
        # Initially hide key field
        self.toggle_ssh_auth()
        
        # Buttons
        button_frame = tk.Frame(main_frame)
        button_frame.grid(row=6, column=0, columnspan=2, pady=10)
        
        save_text = "Update" if self.is_edit else "Add"
        tk.Button(
            button_frame, text=save_text, command=self.save_ssh_connection
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            button_frame, text="Cancel", command=self.destroy
        ).pack(side=tk.LEFT, padx=5)
    
    def toggle_ssh_auth(self):
        """Toggle between password and SSH key authentication"""
        if self.ssh_auth_var.get() == "password":
            self.ssh_password_label.grid(row=5, column=0, sticky="e", padx=5, pady=5)
            self.ssh_password_entry.grid(row=5, column=1, padx=5, pady=5)
            self.ssh_key_label.grid_forget()
            self.ssh_key_entry.grid_forget()
        else:
            self.ssh_password_label.grid_forget()
            self.ssh_password_entry.grid_forget()
            self.ssh_key_label.grid(row=5, column=0, sticky="e", padx=5, pady=5)
            self.ssh_key_entry.grid(row=5, column=1, padx=5, pady=5)
    
    def load_connection_data(self):
        """Load existing connection data into form fields"""
        if self.connection_type == "odoo":
            self.load_odoo_data()
        else:
            self.load_ssh_data()
    
    def load_odoo_data(self):
        """Load existing Odoo connection data"""
        if not self.connection_data:
            return
            
        self.name_entry.insert(0, self.connection_data.get('name', ''))
        self.host_entry.insert(0, self.connection_data.get('host', ''))
        self.port_entry.delete(0, tk.END)
        self.port_entry.insert(0, str(self.connection_data.get('port', 5432)))
        self.database_entry.insert(0, self.connection_data.get('database', ''))
        self.username_entry.insert(0, self.connection_data.get('username', ''))
        self.password_entry.insert(0, self.connection_data.get('password', ''))
        self.filestore_entry.insert(0, self.connection_data.get('filestore_path', ''))
        
        # Odoo version
        odoo_version = self.connection_data.get('odoo_version', '17.0')
        self.odoo_version_combo.set(odoo_version)
        
        # Local development flag
        self.is_local_var.set(self.connection_data.get('is_local', False))
        
        # SSH connection
        ssh_id = self.connection_data.get('ssh_connection_id')
        if ssh_id:
            # SSH is enabled
            self.use_ssh_var.set(True)
            # Find the SSH connection name by ID
            for name, conn_id in self.ssh_connection_map.items():
                if conn_id == ssh_id:
                    self.ssh_combo.set(name)
                    break
            # Enable the SSH dropdown
            self.ssh_combo.config(state="readonly")
            # Disable the browse button since SSH is used
            self.browse_button.config(state="disabled")
        else:
            self.use_ssh_var.set(False)
            self.ssh_combo.config(state="disabled")
            self.browse_button.config(state="normal")
        
        # Allow restore flag
        self.allow_restore_var.set(self.connection_data.get('allow_restore', False))
    
    def load_ssh_data(self):
        """Load existing SSH connection data"""
        if not self.connection_data:
            return
            
        self.ssh_name_entry.insert(0, self.connection_data.get('name', ''))
        self.ssh_host_entry.insert(0, self.connection_data.get('host', ''))
        self.ssh_port_entry.delete(0, tk.END)
        self.ssh_port_entry.insert(0, str(self.connection_data.get('port', 22)))
        self.ssh_username_entry.insert(0, self.connection_data.get('username', ''))
        
        # Authentication
        if self.connection_data.get('ssh_key_path'):
            self.ssh_auth_var.set("key")
            self.ssh_key_entry.insert(0, self.connection_data.get('ssh_key_path', ''))
        else:
            self.ssh_auth_var.set("password")
            self.ssh_password_entry.insert(0, self.connection_data.get('password', ''))
        
        self.toggle_ssh_auth()
    
    def validate_odoo_fields(self):
        """Validate Odoo connection fields"""
        if not self.name_entry.get().strip():
            messagebox.showerror("Error", "Connection name is required")
            return False
        
        if not self.host_entry.get().strip():
            messagebox.showerror("Error", "Host is required")
            return False
        
        if not self.database_entry.get().strip():
            messagebox.showerror("Error", "Database name is required")
            return False
        
        if not self.username_entry.get().strip():
            messagebox.showerror("Error", "Username is required")
            return False
        
        try:
            port = int(self.port_entry.get())
            if port < 1 or port > 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Port must be a valid number (1-65535)")
            return False
        
        return True
    
    def validate_ssh_fields(self):
        """Validate SSH connection fields"""
        if not self.ssh_name_entry.get().strip():
            messagebox.showerror("Error", "Connection name is required")
            return False
        
        if not self.ssh_host_entry.get().strip():
            messagebox.showerror("Error", "Host is required")
            return False
        
        if not self.ssh_username_entry.get().strip():
            messagebox.showerror("Error", "Username is required")
            return False
        
        try:
            port = int(self.ssh_port_entry.get())
            if port < 1 or port > 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Port must be a valid number (1-65535)")
            return False
        
        if self.ssh_auth_var.get() == "password":
            if not self.ssh_password_entry.get():
                messagebox.showerror("Error", "Password is required")
                return False
        else:
            if not self.ssh_key_entry.get().strip():
                messagebox.showerror("Error", "SSH key path is required")
                return False
        
        return True
    
    def toggle_ssh_controls(self):
        """Toggle SSH dropdown and browse button based on checkbox"""
        if self.use_ssh_var.get():
            # SSH enabled - enable dropdown, disable browse button
            self.ssh_combo.config(state="readonly")
            self.browse_button.config(state="disabled")
        else:
            # SSH disabled - disable dropdown, enable browse button
            self.ssh_combo.config(state="disabled")
            self.browse_button.config(state="normal")
    
    def browse_folder(self):
        """Browse for folder selection"""
        from tkinter import filedialog
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.filestore_entry.delete(0, tk.END)
            self.filestore_entry.insert(0, folder_path)
    
    def load_from_odoo_conf(self):
        """Load configuration from odoo.conf file"""
        from tkinter import filedialog
        import configparser
        
        conf_file = filedialog.askopenfilename(
            title="Select Odoo Configuration File",
            filetypes=[("Config files", "*.conf"), ("All files", "*.*")]
        )
        
        if not conf_file:
            return
        
        try:
            config = configparser.ConfigParser()
            config.read(conf_file)
            
            if 'options' in config:
                options = config['options']
                
                # Database settings
                if 'db_host' in options:
                    self.host_entry.delete(0, tk.END)
                    self.host_entry.insert(0, options['db_host'])
                
                if 'db_port' in options:
                    self.port_entry.delete(0, tk.END)
                    self.port_entry.insert(0, options['db_port'])
                
                if 'db_name' in options:
                    self.database_entry.delete(0, tk.END)
                    self.database_entry.insert(0, options['db_name'])
                
                if 'db_user' in options:
                    self.username_entry.delete(0, tk.END)
                    self.username_entry.insert(0, options['db_user'])
                
                if 'db_password' in options:
                    self.password_entry.delete(0, tk.END)
                    self.password_entry.insert(0, options['db_password'])
                
                if 'data_dir' in options:
                    self.filestore_entry.delete(0, tk.END)
                    self.filestore_entry.insert(0, options['data_dir'])
                
                messagebox.showinfo("Success", "Configuration loaded from odoo.conf")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load configuration: {str(e)}")
    
    def test_connection(self):
        """Test the connection configuration"""
        if hasattr(self.parent, 'test_connection_config'):
            # Gather current field values
            fields = {
                'host': self.host_entry,
                'port': self.port_entry,
                'database': self.database_entry,
                'username': self.username_entry,
                'password': self.password_entry,
                'use_ssh': self.use_ssh_var,
                'ssh_connection': self.ssh_combo
            }
            self.parent.test_connection_config(fields)
        else:
            messagebox.showinfo("Test", "Connection test not implemented")
    
    def save_odoo_connection(self):
        """Save Odoo connection"""
        if not self.validate_odoo_fields():
            return
        
        # Get SSH connection ID if SSH is enabled
        ssh_connection_id = None
        if self.use_ssh_var.get() and self.ssh_combo.get():
            selected_ssh_name = self.ssh_combo.get()
            if selected_ssh_name in self.ssh_connection_map:
                ssh_connection_id = self.ssh_connection_map[selected_ssh_name]
        
        self.result = {
            'name': self.name_entry.get().strip(),
            'host': self.host_entry.get().strip(),
            'port': int(self.port_entry.get()),
            'database': self.database_entry.get().strip(),
            'username': self.username_entry.get().strip(),
            'password': self.password_entry.get(),
            'filestore_path': self.filestore_entry.get().strip(),
            'odoo_version': self.odoo_version_combo.get(),
            'is_local': self.is_local_var.get(),
            'ssh_connection_id': ssh_connection_id,
            'allow_restore': self.allow_restore_var.get()
        }
        
        self.destroy()
    
    def save_ssh_connection(self):
        """Save SSH connection"""
        if not self.validate_ssh_fields():
            return
        
        self.result = {
            'name': self.ssh_name_entry.get().strip(),
            'host': self.ssh_host_entry.get().strip(),
            'port': int(self.ssh_port_entry.get()),
            'username': self.ssh_username_entry.get().strip()
        }
        
        if self.ssh_auth_var.get() == "password":
            self.result['password'] = self.ssh_password_entry.get()
            self.result['ssh_key_path'] = None
        else:
            self.result['password'] = None
            self.result['ssh_key_path'] = self.ssh_key_entry.get().strip()
        
        self.destroy()