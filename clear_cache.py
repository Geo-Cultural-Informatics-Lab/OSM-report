#!/usr/bin/env python
"""
Clear all Python cache files (.pyc and __pycache__ directories).
Run this if you encounter import errors after code changes.
"""

import os
import shutil
from pathlib import Path

def clear_cache(root_dir="."):
    """Clear all Python cache files recursively."""
    root = Path(root_dir)
    deleted_dirs = 0
    deleted_files = 0

    print("Clearing Python cache files...")
    print(f"Root directory: {root.resolve()}")
    print()

    # Remove __pycache__ directories
    for pycache_dir in root.rglob("__pycache__"):
        try:
            shutil.rmtree(pycache_dir)
            deleted_dirs += 1
            print(f"  Removed: {pycache_dir.relative_to(root)}")
        except Exception as e:
            print(f"  Failed to remove {pycache_dir}: {e}")

    # Remove .pyc files
    for pyc_file in root.rglob("*.pyc"):
        try:
            pyc_file.unlink()
            deleted_files += 1
            print(f"  Removed: {pyc_file.relative_to(root)}")
        except Exception as e:
            print(f"  Failed to remove {pyc_file}: {e}")

    print()
    print(f"Done! Removed {deleted_dirs} __pycache__ directories and {deleted_files} .pyc files")
    print()
    print("You can now run your code with a clean cache.")

if __name__ == "__main__":
    clear_cache()
