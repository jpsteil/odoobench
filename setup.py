"""
Setup script for OdooBench
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the contents of README file
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text() if (this_directory / "README.md").exists() else ""

# Read version from __init__.py
def get_version():
    version_file = this_directory / "odoobench" / "__init__.py"
    version_content = version_file.read_text()
    # Look for __version__ = "x.y.z" or __version__ = 'x.y.z'
    for line in version_content.splitlines():
        if line.startswith('__version__'):
            # Extract the version string between quotes
            if '"' in line:
                return line.split('"')[1]
            elif "'" in line:
                return line.split("'")[1]
    raise RuntimeError("Unable to find version string.")

setup(
    name="odoobench",
    version=get_version(),
    author="Jim Steil",
    description="A comprehensive backup and restore utility for Odoo instances",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/jpsteil/odoobench",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: System Administrators",
        "Topic :: System :: Archiving :: Backup",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    install_requires=[
        "cryptography>=41.0.0",
        "paramiko>=3.0.0",
    ],
    extras_require={
        "gui": ["tkinter"],  # Note: tkinter usually comes with Python
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "odoobench=odoobench.cli:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
