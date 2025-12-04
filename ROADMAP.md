# OdooBench Roadmap

## Vision

Transform OdooBench from a backup/restore utility into a comprehensive **Odoo Instance Manager** - a single tool for managing multiple Odoo installations across local and remote servers.

## Architecture Overview

### New Layout Design

```
┌──────────────┬──────────────────────────────────────────────────────────┐
│ Connections  │  [prod-01] [staging] [dev-box]         (connection tabs) │
│              ├──────────────────────────────────────────────────────────┤
│ 📁 Production│  [Logs] [Modules] [Database] [Config] [Backup] [Restore] │
│   ○ prod-01  ├──────────────────────────────────────────────────────────┤
│ 📁 Staging   │                                                          │
│   ○ staging  │              Feature Content Area                        │
│ 📁 Local     │                                                          │
│   ● dev-box  │                                                          │
│              │                                                          │
│ [+] Add      │                                                          │
└──────────────┴──────────────────────────────────────────────────────────┘
```

- **Left pane**: Connection tree organized by groups (collapsible)
- **Outer tabs**: One tab per open connection (like browser tabs)
- **Inner tabs**: Feature tabs within each connection (Logs, Modules, etc.)

### Core Concept

**One connection = One Odoo instance**

Even if multiple Odoo instances run on the same physical server, each appears as a separate connection (same host, different odoo.conf paths).

---

## Completed Features ✅

### Phase 1: Foundation
- [x] **ConnectionExecutor abstraction** (`odoobench/core/executor.py`)
  - `LocalExecutor` - execute commands on local machine via subprocess
  - `SSHExecutor` - execute commands on remote machines via paramiko
  - Unified interface: `run_command()`, `read_file()`, `write_file()`, `tail_file()`, `tail_file_follow()`

### Phase 2: Connection Management
- [x] **OdooInstanceManager** (`odoobench/db/odoo_connection_manager.py`)
  - Unified schema combining SSH + Odoo config + database connection
  - Encrypted password storage (SSH and database passwords)
  - Group organization for connections
  - Import/export connections as JSON (without passwords)
  - Settings persistence (dark mode, font size, backup directory, window geometry)

### Phase 3: Auto-Discovery
- [x] **OdooConfigParser** (`odoobench/core/odoo_config_parser.py`)
  - Parse odoo.conf files to extract settings
  - Auto-discover: log path, filestore path, database connection, addons path
  - Find odoo.conf in common locations
  - Database connection testing
  - Service status checking

### Phase 4: New GUI
- [x] **InstanceWindow** (`odoobench/gui/instance_window.py`)
  - Left pane with connection tree (grouped)
  - Outer tabs for open connections
  - Inner tabs for features per connection
  - Dark mode (Darcula-inspired theme)
  - Font size adjustment (8-18)
  - Window geometry persistence (position, size, sash positions)
  - Settings dialog (File > Settings)

### Phase 5: Log Viewer
- [x] **Logs Tab** - fully implemented
  - Load N lines from remote/local log file
  - Follow mode (tail -f style, real-time updates)
  - Filter by text (search)
  - Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  - Color-coded log levels
  - Right-click context menu (Select All, Copy, Cut, Paste)
  - Keyboard shortcuts (Ctrl+A, Ctrl+C)

### Phase 6: Backup/Restore Integration
- [x] **Backup Tab** - fully implemented
  - Backup types: Complete (DB + Filestore), Database-only, Filestore-only
  - Custom backup directory with browse dialog
  - Progress bar with real-time status updates
  - Color-coded log output (error, warning, success, info)
  - SSH remote filestore support via paramiko
  - Threaded operation (non-blocking UI)

- [x] **Restore Tab** - fully implemented (only shown when restore enabled)
  - Restore from backup file with browse dialog
  - Recent backups list with auto-refresh
  - Restore types: Complete, Database-only, Filestore-only
  - Database neutralization option (disables email, crons, payments)
  - Production protection (confirmation dialogs for production instances)
  - Progress bar with real-time log output
  - SSH remote filestore restore support

- [x] **Backup & Restore Tab** - one-shot operation (always available)
  - Backup FROM current connection, restore TO another connection
  - Destination dropdown shows only connections with restore enabled
  - Displays destination details with production warnings
  - Complete, Database-only, or Filestore-only transfer
  - Neutralization option for destination
  - Progress bar with combined operation log
  - Uses backup_and_restore() for efficient single operation

---

## Planned Features 🚧

### Phase 7: Database Tab
- [ ] Database size breakdown (tables, indexes, bloat)
- [ ] List active cron jobs with last run times
- [ ] Show pending/failed mail queue count
- [ ] View active user sessions
- [ ] Identify long-running queries
- [ ] Check sequence gaps
- [ ] Quick database actions (vacuum, reindex)

### Phase 8: Module Manager Tab
- [ ] List all installed/uninstalled modules
- [ ] Show module dependencies tree
- [ ] Compare modules between two databases
- [ ] Identify orphan/broken modules
- [ ] Quick upgrade/install via XML-RPC
- [ ] Module search and filter

### Phase 9: Config Tab
- [ ] View odoo.conf with syntax highlighting
- [ ] Diff odoo.conf between environments
- [ ] Compare system parameters (ir.config_parameter)
- [ ] Show differences in company settings
- [ ] Export/import specific config sections
- [ ] Highlight security-sensitive changes

### Phase 10: Health Monitor Tab
- [ ] Service status (running/stopped)
- [ ] Database connectivity indicator
- [ ] Disk space monitoring (filestore, backups, logs)
- [ ] Memory/CPU usage (if accessible)
- [ ] Last backup timestamp
- [ ] Odoo version display
- [ ] Alert indicators (disk full, service down)
- [ ] Auto-refresh option

---

## Database Schema

### odoo_instances table
```sql
CREATE TABLE odoo_instances (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,

    -- SSH/Connection details
    host TEXT DEFAULT 'localhost',
    ssh_port INTEGER DEFAULT 22,
    ssh_username TEXT,
    ssh_password TEXT,          -- encrypted
    ssh_key_path TEXT,
    is_local BOOLEAN DEFAULT 0,

    -- Odoo paths
    odoo_conf_path TEXT,
    log_path TEXT,
    filestore_path TEXT,
    addons_path TEXT,

    -- Database connection
    db_host TEXT DEFAULT 'localhost',
    db_port INTEGER DEFAULT 5432,
    db_user TEXT DEFAULT 'odoo',
    db_password TEXT,           -- encrypted
    db_name TEXT,

    -- Metadata
    is_production BOOLEAN DEFAULT 0,
    allow_restore BOOLEAN DEFAULT 0,
    group_name TEXT,
    notes TEXT,

    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### settings table
```sql
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP
);
```

Settings stored:
- `dark_mode` - "0" or "1"
- `font_size` - "8" to "18"
- `backup_directory` - path string
- `window_geometry` - "WxH+X+Y" format
- `layout_main_sash` - left pane width in pixels
- `last_active_tab` - index of last selected connection tab

---

## File Structure

```
odoobench/
├── core/
│   ├── backup_restore.py      # Existing backup/restore logic
│   ├── executor.py            # NEW: SSH/Local command execution
│   └── odoo_config_parser.py  # NEW: Parse odoo.conf
├── db/
│   ├── connection_manager.py  # Existing (legacy DB connections)
│   └── odoo_connection_manager.py  # NEW: Unified instance management
├── gui/
│   ├── main_window.py         # OLD: Original GUI (to be deprecated)
│   ├── instance_window.py     # NEW: Main instance manager GUI
│   └── dialogs/
│       ├── connection_dialog.py
│       └── progress_dialog.py
├── cli.py
├── gui_launcher.py            # Updated to launch new GUI
└── version.py
```

---

## Running the Application

```bash
# Development
make run          # Runs new Instance Manager GUI
make run-cli      # Runs CLI

# After installation
odoobench         # CLI
odoobench-gui     # GUI (if entry point added)
```

---

## Design Decisions

1. **One connection = One Odoo instance**: Simplifies mental model. Multiple instances on same server = multiple connections.

2. **SSH as foundation**: Everything flows from "I'm connected to a machine running Odoo". Local is just SSH without the SSH.

3. **Auto-discovery**: Parse odoo.conf to reduce manual configuration. User can override any discovered value.

4. **Backup files stay local**: Your machine is the hub. Backups download to local, restores upload from local.

5. **Production protection**: Default disable restore on production connections. Explicit opt-in required.

6. **Nested tabs (Option A)**: Connection tabs contain feature tabs. Matches mental model of "I'm on server X, looking at logs".

---

## Future Considerations

- **Detachable tabs**: Pop out a connection to its own window (multi-monitor)
- **Side-by-side comparison**: Split view to compare two servers
- **Scheduled backups**: Cron-like scheduling for automated backups
- **Notifications**: Desktop notifications for long-running operations
- **Plugin system**: Allow custom tabs/features
