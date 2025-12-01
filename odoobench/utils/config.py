"""
Configuration management for OdooBench
"""

import os
import json
from pathlib import Path


class Config:
    """Configuration manager for the application"""

    DEFAULT_CONFIG = {
        "backup_dir": str(Path.home() / "Documents" / "OdooBackups"),
        "default_odoo_version": "17.0",
        "pg_dump_options": ["--no-owner", "--no-acl"],
        "compression_level": 6,
        "max_backup_age_days": 30,
        "auto_cleanup": False,
        "verbose": False,
    }

    def __init__(self, config_file=None):
        """Initialize configuration"""
        if config_file is None:
            # Use new location
            config_dir = Path.home() / ".config" / "odoobench"
            old_config_dir = Path.home() / ".config" / "odoo-backup-manager"

            config_dir.mkdir(parents=True, exist_ok=True)
            config_file = config_dir / "config.json"

            # Migrate old config if it exists
            old_config_file = old_config_dir / "config.json"
            if not config_file.exists() and old_config_file.exists():
                import shutil
                shutil.copy2(old_config_file, config_file)
                print(f"Migrated config from old location to {config_file}")

        self.config_file = Path(config_file)
        self.config = self.load_config()

    def load_config(self):
        """Load configuration from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    user_config = json.load(f)
                    # Merge with defaults
                    config = self.DEFAULT_CONFIG.copy()
                    config.update(user_config)
                    return config
            except Exception as e:
                print(f"Error loading config: {e}")
                return self.DEFAULT_CONFIG.copy()
        else:
            # Create default config file
            self.save_config(self.DEFAULT_CONFIG)
            return self.DEFAULT_CONFIG.copy()

    def save_config(self, config=None):
        """Save configuration to file"""
        if config is None:
            config = self.config

        try:
            with open(self.config_file, "w") as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False

    def get(self, key, default=None):
        """Get configuration value"""
        return self.config.get(key, default)

    def set(self, key, value):
        """Set configuration value"""
        self.config[key] = value
        return self.save_config()

    def update(self, updates):
        """Update multiple configuration values"""
        self.config.update(updates)
        return self.save_config()

    def reset(self):
        """Reset configuration to defaults"""
        self.config = self.DEFAULT_CONFIG.copy()
        return self.save_config()

    def get_backup_dir(self):
        """Get backup directory, creating it if necessary"""
        backup_dir = Path(
            self.config.get("backup_dir", self.DEFAULT_CONFIG["backup_dir"])
        )
        backup_dir.mkdir(parents=True, exist_ok=True)
        return str(backup_dir)
