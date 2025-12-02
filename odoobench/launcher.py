"""Desktop launcher creation for OdooBench."""

import os
import platform
import shutil
import sys
from pathlib import Path


def get_executable_path():
    """Get the path to the odoobench executable."""
    return shutil.which("odoobench") or sys.executable


def get_icon_path():
    """Get the path to the bundled icon."""
    package_dir = Path(__file__).parent
    return package_dir / "resources" / "odoobench.png"


def install_icon_linux():
    """Install the icon to the standard Linux icon location."""
    icon_source = get_icon_path()
    if not icon_source.exists():
        print(f"Warning: Icon not found at {icon_source}")
        return None

    # Install to user's icon directory
    icon_dir = Path.home() / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps"
    icon_dir.mkdir(parents=True, exist_ok=True)

    icon_dest = icon_dir / "odoobench.png"
    shutil.copy2(icon_source, icon_dest)

    # Update icon cache (optional, may not work without root)
    try:
        os.system("gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor 2>/dev/null")
    except Exception:
        pass

    return "odoobench"  # Return icon name for .desktop file


def create_linux_launcher():
    """Create a .desktop file for Linux."""
    desktop_dir = os.path.expanduser("~/.local/share/applications")
    os.makedirs(desktop_dir, exist_ok=True)

    desktop_file = os.path.join(desktop_dir, "odoobench.desktop")

    # Get executable path
    exec_path = shutil.which("odoobench")
    if not exec_path:
        exec_path = f"{sys.executable} -m odoobench.cli"

    # Install icon and get icon name/path
    icon_name = install_icon_linux()
    if not icon_name:
        # Fallback to bundled icon path or generic icon
        icon_path = get_icon_path()
        icon_name = str(icon_path) if icon_path.exists() else "utilities-terminal"

    content = f"""[Desktop Entry]
Name=OdooBench
Comment=Odoo Backup and Restore Utility
Exec={exec_path}
Icon={icon_name}
Type=Application
Categories=Development;Database;Utility;
Terminal=false
StartupWMClass=odoobench
"""

    with open(desktop_file, "w") as f:
        f.write(content)

    os.chmod(desktop_file, 0o755)

    print(f"Created Linux desktop launcher: {desktop_file}")
    print("Icon installed to ~/.local/share/icons/hicolor/256x256/apps/odoobench.png")
    return True


def create_macos_launcher():
    """Create an application launcher for macOS."""
    app_base = os.path.expanduser("~/Applications/OdooBench.app/Contents")
    app_dir = os.path.join(app_base, "MacOS")
    resources_dir = os.path.join(app_base, "Resources")
    os.makedirs(app_dir, exist_ok=True)
    os.makedirs(resources_dir, exist_ok=True)

    # Get executable path
    exec_path = shutil.which("odoobench")
    if not exec_path:
        exec_path = f"{sys.executable} -m odoobench.cli"

    # Create the launcher script
    launcher_script = os.path.join(app_dir, "OdooBench")
    content = f"""#!/bin/bash
exec {exec_path}
"""

    with open(launcher_script, "w") as f:
        f.write(content)
    os.chmod(launcher_script, 0o755)

    # Copy icon to Resources
    icon_source = get_icon_path()
    icon_dest = os.path.join(resources_dir, "odoobench.png")
    if icon_source.exists():
        shutil.copy2(icon_source, icon_dest)

    # Create Info.plist
    plist_file = os.path.join(app_base, "Info.plist")
    plist_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>OdooBench</string>
    <key>CFBundleIdentifier</key>
    <string>com.odoobench.app</string>
    <key>CFBundleName</key>
    <string>OdooBench</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleIconFile</key>
    <string>odoobench.png</string>
</dict>
</plist>
"""

    with open(plist_file, "w") as f:
        f.write(plist_content)

    print(f"Created macOS application: ~/Applications/OdooBench.app")
    return True


def create_windows_launcher():
    """Create a Start Menu shortcut for Windows."""
    try:
        start_menu = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"

        if not start_menu.exists():
            print(f"Could not find Start Menu folder: {start_menu}")
            return False

        exec_path = shutil.which("odoobench.exe") or shutil.which("odoobench")
        if not exec_path:
            exec_path = f'"{sys.executable}" -m odoobench.cli'

        bat_file = start_menu / "OdooBench.bat"
        content = f"""@echo off
start "" {exec_path}
"""

        with open(bat_file, "w") as f:
            f.write(content)

        print(f"Created Windows Start Menu launcher: {bat_file}")
        return True

    except Exception as e:
        print(f"Failed to create Windows launcher: {e}")

        # Fallback: create on Desktop
        desktop = os.path.expanduser("~/Desktop")
        if os.path.exists(desktop):
            exec_path = shutil.which("odoobench.exe") or shutil.which("odoobench")
            if not exec_path:
                exec_path = f'"{sys.executable}" -m odoobench.cli'

            bat_file = os.path.join(desktop, "OdooBench.bat")
            content = f"""@echo off
start "" {exec_path}
"""
            with open(bat_file, "w") as f:
                f.write(content)

            print(f"Created Desktop launcher instead: {bat_file}")
            return True

        return False


def create_launcher():
    """Create a desktop launcher appropriate for the current OS."""
    system = platform.system().lower()

    print(f"Detected OS: {platform.system()}")

    if system == "linux":
        return create_linux_launcher()
    elif system == "darwin":
        return create_macos_launcher()
    elif system == "windows":
        return create_windows_launcher()
    else:
        print(f"Unsupported operating system: {system}")
        return False


def remove_launcher():
    """Remove the desktop launcher for the current OS."""
    system = platform.system().lower()

    if system == "linux":
        removed = False
        desktop_file = os.path.expanduser("~/.local/share/applications/odoobench.desktop")
        if os.path.exists(desktop_file):
            os.remove(desktop_file)
            print(f"Removed: {desktop_file}")
            removed = True

        # Also remove the icon
        icon_file = os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps/odoobench.png")
        if os.path.exists(icon_file):
            os.remove(icon_file)
            print(f"Removed: {icon_file}")
            removed = True

        if not removed:
            print("No Linux launcher found.")
            return False
        return True

    elif system == "darwin":
        app_dir = os.path.expanduser("~/Applications/OdooBench.app")
        if os.path.exists(app_dir):
            shutil.rmtree(app_dir)
            print(f"Removed: {app_dir}")
            return True
        else:
            print("No macOS launcher found.")
            return False

    elif system == "windows":
        start_menu = os.path.join(
            os.environ.get("APPDATA", ""),
            "Microsoft", "Windows", "Start Menu", "Programs", "OdooBench.bat"
        )
        desktop = os.path.expanduser("~/Desktop/OdooBench.bat")

        removed = False
        if os.path.exists(start_menu):
            os.remove(start_menu)
            print(f"Removed: {start_menu}")
            removed = True
        if os.path.exists(desktop):
            os.remove(desktop)
            print(f"Removed: {desktop}")
            removed = True

        if not removed:
            print("No Windows launcher found.")
        return removed

    else:
        print(f"Unsupported operating system: {system}")
        return False
