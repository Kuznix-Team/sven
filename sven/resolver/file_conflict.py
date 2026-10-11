# ============================================================
#  Sven — Seven OS Package Manager
#  HANS TECH © 2024 — GPL v3
#  resolver/file_conflict.py — file-level conflict detection
# ============================================================
#
#  Before extracting a package archive, check every file against
#  the local DB to ensure no file is already owned by another
#  package. Prevents silent overwrites and system corruption.
# ============================================================

import tarfile
from pathlib import Path
from typing import Iterable, Optional

from ..db.local_db import LocalDB
from ..db.models import Package
from ..exceptions import FileConflictError


def get_package_file_list(archive_path: str) -> list[str]:
    """
    Extract the file list from a .pkg.tar.zst archive.
    Returns a list of file paths (relative, no leading /).
    """
    files = []
    try:
        with tarfile.open(archive_path, "r:*") as tar:
            for member in tar.getmembers():
                # Directories are shared by design (usr/include/foo, usr/lib,
                # ...). Like pacman, never treat them as file conflicts.
                if member.isdir():
                    continue
                name = member.name
                # Skip metadata files
                if name.startswith("."):
                    continue
                # Normalise: strip leading ./ and /
                name = name.lstrip("./")
                if name:
                    files.append(name)
    except (tarfile.TarError, OSError):
        pass
    return files


# Arch splits some monolithic upstream packages into several. On an LFS
# system the monolith is what got adopted into the local DB, so the split
# package legitimately overlaps with it. Map: split package -> parent.
SPLIT_PACKAGE_PARENTS = {
    "util-linux-libs": "util-linux",
    "systemd-libs": "systemd",
    "gcc-libs": "gcc",
}


def is_split_sibling(owner: str, new_pkg: str) -> bool:
    """True if *new_pkg* is an Arch split-out piece of *owner*."""
    if SPLIT_PACKAGE_PARENTS.get(new_pkg) == owner:
        return True
    return new_pkg == f"{owner}-libs"


def check_file_conflicts(
    pkg: Package,
    archive_path: str,
    local_db: LocalDB,
    force: bool = False,
    allow_split_takeover: bool = False,
    protected_packages: Iterable[str] = (),
    force_protected: bool = False,
) -> list[dict]:
    """
    Check if any file in the package archive conflicts with
    files owned by already-installed packages.

    Args:
        pkg: The package being installed
        archive_path: Path to the .pkg.tar.zst file
        local_db: The local installed package database
        force: If True, report conflicts but don't raise
        allow_split_takeover: If True, files owned by the monolithic parent
            of an Arch split package (e.g. util-linux -> util-linux-libs)
            are not errors; they are returned flagged ``takeover=True`` so
            the caller can move ownership to the new package.
        protected_packages / force_protected: a takeover from a protected
            package additionally requires ``force_protected``.

    Returns:
        List of conflict dicts: [{file, owner, new_pkg, takeover}, ...]

    Raises:
        FileConflictError if non-takeover conflicts are found and force=False.
        The error carries the first conflict and a ``total`` count.
    """
    new_files = get_package_file_list(archive_path)
    if not new_files:
        return []

    from ..libsven import ConflictContext

    ctx = ConflictContext()
    for other_pkg in local_db.all_packages():
        if other_pkg.name == pkg.name:
            continue
        for f in local_db.get_files(other_pkg.name):
            ctx.add(f, other_pkg.name)

    protected = set(protected_packages)
    conflicts = []
    for filepath in new_files:
        owner = ctx.owner(filepath)
        if not owner or owner == pkg.name:
            continue
        takeover = (
            allow_split_takeover
            and is_split_sibling(owner, pkg.name)
            and (owner not in protected or force_protected)
        )
        conflicts.append({
            "file": filepath,
            "owner": owner,
            "new_pkg": pkg.name,
            "takeover": takeover,
        })

    blocking = [c for c in conflicts if not c["takeover"]]
    if blocking and not force:
        first = blocking[0]
        raise FileConflictError(
            filename=first["file"],
            owner_pkg=first["owner"],
            new_pkg=first["new_pkg"],
            total=len(blocking),
        )

    return conflicts


def check_internal_conflicts(packages: list[Package], archives: dict[str, str]) -> list[dict]:
    """
    Check if multiple NEW packages being installed contain
    the same files (conflict between packages in the same transaction).

    Args:
        packages: List of packages being installed
        archives: Dict of {pkg_name: archive_path}

    Returns:
        List of conflict dicts
    """
    file_to_pkg: dict[str, str] = {}
    conflicts = []

    for pkg in packages:
        archive = archives.get(pkg.name)
        if not archive:
            continue

        files = get_package_file_list(archive)
        for filepath in files:
            if filepath in file_to_pkg:
                other = file_to_pkg[filepath]
                if other != pkg.name:
                    conflicts.append({
                        "file": filepath,
                        "owner": other,
                        "new_pkg": pkg.name,
                    })
            else:
                file_to_pkg[filepath] = pkg.name

    return conflicts
