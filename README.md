# OdooBench

[![PyPI version](https://badge.fury.io/py/odoobench.svg)](https://pypi.org/project/odoobench/)
[![Python versions](https://img.shields.io/pypi/pyversions/odoobench.svg)](https://pypi.org/project/odoobench/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A comprehensive backup and restore utility for Odoo instances with smart GUI/CLI interface, supporting both database and filestore operations with local and remote (SSH) connections.

## Features

- **Smart Interface**: Automatically launches GUI when available, falls back to CLI
- **Complete Backup & Restore**: Handles both PostgreSQL database and Odoo filestore
- **Secure Storage**: Encrypted password storage for connection profiles
- **Remote Support**: Backup/restore from remote servers via SSH
- **Connection Profiles**: Save and reuse connection configurations
- **Dual Interface**: Both GUI and CLI modes available
- **Archive Management**: Creates compressed archives with metadata
- **Flexible Operations**: Backup only, restore only, or backup & restore in one operation
- **Production Protection**: Prevent accidental restores to production databases
- **Database Neutralization**: Safe testing with disabled emails, crons, and payment providers

## Installation

### Using pip (Recommended)

```bash
pip install odoobench
```

### From Source

```bash
# Clone the repository
git clone https://github.com/jpsteil/odoobench.git
cd odoobench

# Install the package
pip install -e .

# For development
pip install -r requirements-dev.txt
```

## Prerequisites

- Python 3.8 or higher
- PostgreSQL client tools (`pg_dump`, `pg_restore`, `psql`)
- tar command-line utility
- tkinter (for GUI mode) - usually included with Python

### Installing PostgreSQL Client Tools

#### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install postgresql-client
```

#### RHEL/CentOS/Fedora
```bash
sudo dnf install postgresql
```

#### macOS
```bash
brew install postgresql
```

## Quick Start

### Default Behavior

```bash
# Launch the application (GUI if available, otherwise help)
odoobench

# Force GUI mode (error if not available)
odoobench --gui

# Force CLI mode
odoobench --cli

# Show CLI help
odoobench --cli --help
```

### GUI Mode

The GUI automatically launches when:
- You run `odoobench` without arguments
- A display is available (not SSH/Docker)
- tkinter is installed

The GUI provides:
- Visual connection management
- Easy backup/restore operations
- Progress tracking
- Connection testing
- Safety features clearly visible

### CLI Mode

The CLI is used when:
- You explicitly use `--cli` flag
- No display is available (SSH, Docker, CI/CD)
- Running in scripts or automation

## Connection Profiles (Recommended)

### Save Connection Profiles

```bash
# Production connection (restore disabled by default for safety)
odoobench --cli connections save \
  --name prod \
  --host db.example.com \
  --user odoo \
  --database mydb \
  --filestore /var/lib/odoo

# Development connection (with restore enabled)
odoobench --cli connections save \
  --name dev \
  --host localhost \
  --user odoo \
  --database devdb \
  --filestore /var/lib/odoo \
  --allow-restore
```

### Use Connection Profiles

```bash
# Backup using connection
odoobench --cli backup --connection prod

# Restore using connection (only works if --allow-restore was set)
odoobench --cli restore --connection dev --file backup.tar.gz --name test_db

# Restore with neutralization for safe testing
odoobench --cli restore --connection dev --file backup.tar.gz --name test_db --neutralize
```

### List Connections

```bash
odoobench --cli connections list
```

## Manual Operations (Without Profiles)

### Backup Operations

```bash
# Backup database and filestore
odoobench --cli backup \
  --name mydb \
  --host localhost \
  --user odoo \
  --filestore /var/lib/odoo/filestore

# Backup database only
odoobench --cli backup \
  --name mydb \
  --host localhost \
  --user odoo \
  --no-filestore

# Backup with specific output directory
odoobench --cli backup \
  --name mydb \
  --host localhost \
  --user odoo \
  --output-dir /backups
```

### Restore Operations

```bash
# Restore from backup file
odoobench --cli restore \
  --file backup_MYDB_20240101_120000.tar.gz \
  --name newdb \
  --host localhost \
  --user odoo

# Restore with database neutralization (safe for testing)
odoobench --cli restore \
  --file backup.tar.gz \
  --name testdb \
  --host localhost \
  --user odoo \
  --neutralize
```

## Database Neutralization

When using the `--neutralize` flag during restore, the following safety measures are applied:

- All outgoing mail servers are disabled
- All scheduled actions (crons) are disabled
- Payment acquirers are disabled
- Email queue is cleared
- Company names are prefixed with [TEST]
- Base URL configuration is unfrozen

This ensures your test database won't send emails or execute scheduled tasks.

## Automation & Scripting

### Cron Job Example

```bash
# Add to crontab for daily backups at 2 AM
0 2 * * * /usr/local/bin/odoobench --cli backup --connection prod
```

### Bash Script Example

```bash
#!/bin/bash
# backup-all-databases.sh

DATABASES=("db1" "db2" "db3")
for DB in "${DATABASES[@]}"; do
    odoobench --cli backup --connection prod --name "$DB"
done
```

### Docker Usage

```dockerfile
# In your Dockerfile
RUN pip install odoobench

# In your script
CMD ["odoobench", "--cli", "backup", "--connection", "prod"]
```

### CI/CD Pipeline

```yaml
# .github/workflows/backup.yml
- name: Backup Odoo Database
  run: |
    odoobench --cli backup \
      --name ${{ secrets.DB_NAME }} \
      --host ${{ secrets.DB_HOST }} \
      --user ${{ secrets.DB_USER }} \
      --password ${{ secrets.DB_PASSWORD }}
```

## Configuration

The tool stores its configuration in `~/.config/odoobench/`:
- `config.json`: Application settings
- `connections.db`: Encrypted connection profiles

### Default Configuration

```json
{
  "backup_dir": "~/Documents/OdooBackups",
  "default_odoo_version": "17.0",
  "pg_dump_options": ["--no-owner", "--no-acl"],
  "compression_level": 6,
  "max_backup_age_days": 30,
  "auto_cleanup": false,
  "verbose": false
}
```

## Backup File Structure

Backup archives (`backup_DBNAME_YYYYMMDD_HHMMSS.tar.gz`) contain:
- `database.sql`: PostgreSQL database dump
- `filestore.tar.gz`: Compressed filestore data (if included)
- `metadata.json`: Backup metadata (timestamp, database name, Odoo version)

## Security Features

- **Encrypted Storage**: Passwords are encrypted using machine-specific keys
- **Production Protection**: Connections are protected from restore by default
- **SSH Support**: Key-based and password authentication for remote connections
- **Safe Defaults**: Must explicitly enable restore capability for connections

## Migration from odoo-backup-manager

If you were using `odoo-backup-manager`, OdooBench will automatically migrate your configuration and connections on first run.

## Troubleshooting

### GUI Not Launching

```bash
# Check if display is available
echo $DISPLAY

# Install tkinter if missing
sudo apt-get install python3-tk

# Force CLI mode as fallback
odoobench --cli [command]
```

### Permission Denied

- Ensure read access to filestore directory
- Ensure write access to backup directory
- Check PostgreSQL user permissions

### Connection Issues

```bash
# Test connection manually
psql -h hostname -U username -d database -c "SELECT version();"

# Check SSH access for remote connections
ssh user@host "echo 'SSH connection successful'"
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest`
5. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details

## Support

- **Issues**: [GitHub Issues](https://github.com/jpsteil/odoobench/issues)
- **Discussions**: [GitHub Discussions](https://github.com/jpsteil/odoobench/discussions)
- **PyPI**: [odoobench](https://pypi.org/project/odoobench/)

## Credits

Developed for the Odoo community to simplify backup and restore operations while maintaining safety and ease of use.
