"""Reusable progress dialog for long-running operations"""

import tkinter as tk
from tkinter import ttk
import threading
from typing import Callable, Optional, Any


class ProgressDialog(tk.Toplevel):
    """A reusable progress dialog for threaded operations"""
    
    def __init__(self, parent, title: str, message: str = "", 
                 operation: Optional[Callable] = None,
                 can_cancel: bool = True,
                 indeterminate: bool = False):
        """
        Initialize progress dialog
        
        Args:
            parent: Parent window
            title: Dialog title
            message: Initial message to display
            operation: Function to run in thread (should accept dialog as parameter)
            can_cancel: Whether to show cancel button
            indeterminate: Whether to use indeterminate progress (spinning)
        """
        super().__init__(parent)
        self.parent = parent
        self.title(title)
        self.operation = operation
        self.can_cancel = can_cancel
        self.cancelled = False
        self.result = None
        self.error = None
        
        # Make dialog modal
        self.transient(parent)
        self.grab_set()
        
        # Prevent closing
        self.protocol("WM_DELETE_WINDOW", self.on_cancel if can_cancel else lambda: None)
        
        # Configure dialog
        self.resizable(False, False)
        
        # Create interface
        self.create_widgets(message, indeterminate)
        
        # Center dialog
        self.center_window()
        
        # Start operation if provided
        if operation:
            self.start_operation()
    
    def create_widgets(self, message: str, indeterminate: bool):
        """Create dialog widgets"""
        # Main frame
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Message label
        self.message_label = ttk.Label(main_frame, text=message, wraplength=400)
        self.message_label.pack(pady=(0, 10))
        
        # Progress bar
        mode = "indeterminate" if indeterminate else "determinate"
        self.progress_bar = ttk.Progressbar(main_frame, mode=mode, length=400)
        self.progress_bar.pack(pady=10)
        
        # Details text (optional, initially hidden)
        self.details_frame = ttk.Frame(main_frame)
        self.details_text = tk.Text(self.details_frame, height=6, width=50, 
                                   wrap=tk.WORD, state=tk.DISABLED)
        self.details_scrollbar = ttk.Scrollbar(self.details_frame, 
                                              command=self.details_text.yview)
        self.details_text.config(yscrollcommand=self.details_scrollbar.set)
        
        # Status label
        self.status_label = ttk.Label(main_frame, text="", font=("TkDefaultFont", 9))
        self.status_label.pack(pady=5)
        
        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=(10, 0))
        
        # Show details button
        self.details_button = ttk.Button(button_frame, text="Show Details",
                                        command=self.toggle_details)
        self.details_button.pack(side=tk.LEFT, padx=5)
        self.details_button.config(state=tk.DISABLED)  # Initially disabled
        
        # Cancel button (if enabled)
        if self.can_cancel:
            self.cancel_button = ttk.Button(button_frame, text="Cancel",
                                           command=self.on_cancel)
            self.cancel_button.pack(side=tk.LEFT, padx=5)
        
        # Close button (initially hidden, shown when complete)
        self.close_button = ttk.Button(button_frame, text="Close",
                                      command=self.destroy)
        # Don't pack yet - will show when operation completes
        
        # Start progress animation if indeterminate
        if indeterminate:
            self.progress_bar.start(10)
    
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
    
    def start_operation(self):
        """Start the operation in a background thread"""
        if self.operation:
            thread = threading.Thread(target=self.run_operation, daemon=True)
            thread.start()
    
    def run_operation(self):
        """Run the operation and handle completion"""
        try:
            # Run the operation, passing self so it can update progress
            self.result = self.operation(self)
            
            # Operation completed successfully
            self.after(0, self.on_complete)
        except Exception as e:
            # Operation failed
            self.error = e
            self.after(0, self.on_error)
    
    def update_message(self, message: str):
        """Update the message label"""
        self.after(0, lambda: self.message_label.config(text=message))
    
    def update_progress(self, value: float, message: str = None):
        """
        Update progress bar value (0-100)
        
        Args:
            value: Progress value (0-100)
            message: Optional message to display
        """
        def update():
            if self.progress_bar['mode'] == 'determinate':
                self.progress_bar['value'] = value
            if message:
                self.message_label.config(text=message)
        
        self.after(0, update)
    
    def update_status(self, status: str):
        """Update the status label"""
        self.after(0, lambda: self.status_label.config(text=status))
    
    def add_detail(self, detail: str):
        """Add a line to the details text"""
        def append():
            self.details_text.config(state=tk.NORMAL)
            self.details_text.insert(tk.END, detail + "\n")
            self.details_text.see(tk.END)
            self.details_text.config(state=tk.DISABLED)
            # Enable details button once we have details
            self.details_button.config(state=tk.NORMAL)
        
        self.after(0, append)
    
    def toggle_details(self):
        """Toggle visibility of details text"""
        if self.details_frame.winfo_viewable():
            self.details_frame.pack_forget()
            self.details_button.config(text="Show Details")
        else:
            self.details_frame.pack(pady=10, fill=tk.BOTH, expand=True)
            self.details_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self.details_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self.details_button.config(text="Hide Details")
            # Resize window to accommodate details
            self.update_idletasks()
    
    def on_cancel(self):
        """Handle cancel button click"""
        self.cancelled = True
        self.update_message("Cancelling...")
        self.update_status("Operation cancelled")
        if self.can_cancel and hasattr(self, 'cancel_button'):
            self.cancel_button.config(state=tk.DISABLED)
    
    def on_complete(self):
        """Handle successful completion"""
        # Stop progress animation
        if self.progress_bar['mode'] == 'indeterminate':
            self.progress_bar.stop()
        else:
            self.progress_bar['value'] = 100
        
        self.update_status("Complete")
        
        # Hide cancel button, show close button
        if self.can_cancel and hasattr(self, 'cancel_button'):
            self.cancel_button.pack_forget()
        self.close_button.pack(side=tk.LEFT, padx=5)
        
        # Allow window to be closed
        self.protocol("WM_DELETE_WINDOW", self.destroy)
    
    def on_error(self):
        """Handle operation error"""
        # Stop progress animation
        if self.progress_bar['mode'] == 'indeterminate':
            self.progress_bar.stop()
        
        self.update_message(f"Error: {str(self.error)}")
        self.update_status("Failed")
        
        # Add error to details
        self.add_detail(f"ERROR: {str(self.error)}")
        
        # Hide cancel button, show close button
        if self.can_cancel and hasattr(self, 'cancel_button'):
            self.cancel_button.pack_forget()
        self.close_button.pack(side=tk.LEFT, padx=5)
        
        # Allow window to be closed
        self.protocol("WM_DELETE_WINDOW", self.destroy)
    
    def wait_for_completion(self):
        """Wait for the operation to complete (blocks)"""
        self.wait_window()
        return self.result, self.error


class SimpleProgressDialog(ProgressDialog):
    """Simplified progress dialog for quick operations"""
    
    @classmethod
    def show(cls, parent, title: str, message: str, operation: Callable):
        """
        Show a simple progress dialog and wait for completion
        
        Args:
            parent: Parent window
            title: Dialog title
            message: Message to display
            operation: Function to run
            
        Returns:
            Tuple of (result, error)
        """
        dialog = cls(parent, title, message, operation, can_cancel=False, 
                    indeterminate=True)
        return dialog.wait_for_completion()


class TestConnectionDialog(ProgressDialog):
    """Specialized progress dialog for testing connections"""
    
    def __init__(self, parent, connection_name: str, test_function: Callable):
        """
        Initialize connection test dialog
        
        Args:
            parent: Parent window
            connection_name: Name of connection being tested
            test_function: Function to test connection
        """
        super().__init__(
            parent,
            title="Testing Connection",
            message=f"Testing connection to {connection_name}...",
            operation=test_function,
            can_cancel=False,
            indeterminate=True
        )


class BackupProgressDialog(ProgressDialog):
    """Specialized progress dialog for backup operations"""
    
    def __init__(self, parent, source_name: str, backup_function: Callable):
        """
        Initialize backup progress dialog
        
        Args:
            parent: Parent window
            source_name: Name of source being backed up
            backup_function: Function to perform backup
        """
        super().__init__(
            parent,
            title="Backup in Progress",
            message=f"Backing up {source_name}...",
            operation=backup_function,
            can_cancel=True,
            indeterminate=False
        )


class RestoreProgressDialog(ProgressDialog):
    """Specialized progress dialog for restore operations"""
    
    def __init__(self, parent, destination_name: str, restore_function: Callable):
        """
        Initialize restore progress dialog
        
        Args:
            parent: Parent window
            destination_name: Name of destination being restored to
            restore_function: Function to perform restore
        """
        super().__init__(
            parent,
            title="Restore in Progress",
            message=f"Restoring to {destination_name}...",
            operation=restore_function,
            can_cancel=True,
            indeterminate=False
        )