#!/usr/bin/env python3
"""Check version compatibility across workspace packages (lockstep versioning)."""

import sys
from pathlib import Path
import tomllib


def get_version(pyproject_path):
    """Extract version from pyproject.toml."""
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
        return data["project"]["version"]


def check_compatibility():
    """Check if all packages have identical versions (lockstep)."""
    root = Path(__file__).parent.parent.parent

    packages = {
        "core": root / "packages/core/pyproject.toml",
        "cli": root / "packages/cli/pyproject.toml",
    }

    versions = {}
    for name, path in packages.items():
        if path.exists():
            versions[name] = get_version(path)
            print(f"{name:10} {versions[name]}")

    # Lockstep: all versions must be exactly equal
    unique_versions = set(versions.values())

    if len(unique_versions) > 1:
        print("\n❌ ERROR: Version mismatch detected!")
        print("Lockstep versioning requires all packages to have the same version.")
        print("Run: make bump-version VERSION=X.Y.Z")
        return False

    print(f"\n✅ All packages at version {list(unique_versions)[0]} (lockstep)")
    return True


if __name__ == "__main__":
    if not check_compatibility():
        sys.exit(1)