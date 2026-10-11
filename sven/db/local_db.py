# ============================================================
#  Sven — Seven OS Package Manager
#  HANS TECH © 2024 — GPL v3
#  db/local_db.py — Sven's installed package database
# ============================================================

import os
import time
import json
import fcntl
import shutil
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("sven")


from .models import Package
from ..constants import DB_INSTALLED, DB_LOCK
from ..exceptions import (
    DatabaseLockError,
    DatabaseCorruptError,
    PackageNotInstalledError,
)


# ── LocalDB class ─────────────────────────────────────────────

class LocalDB:
    """
    Manages Sven's database of installed packages.

    Structure:
        /var/lib/sven/installed/
        ├── firefox-125.0-1/
        │   ├── desc         ← metadata (JSON)
        │   └── files        ← newline-separated file list
        ├── gtk3-4.14.2-1/
        │   └── ...
    """

    def __init__(
        self,
        db_path   = None,
        lock_path = None,
    ):
        from .. import constants as C
        logger.debug(f"LocalDB.__init__: root is {db_path or C.DB_INSTALLED}")
        self.db_path   = Path(db_path or C.DB_INSTALLED)
        self.lock_path = Path(lock_path or C.DB_LOCK)
        self.db_path.mkdir(parents=True, exist_ok=True)

        self._lock_fd = None

        # In-memory cache: name → Package
        self._cache : dict[str, Package] = {}
        # Provides map: virtual → real package name
        self._provides : dict[str, str] = {}
        self._loaded = False

    # ── Lock ──────────────────────────────────────────────────

    def acquire_lock(self):
        """
        Acquire exclusive lock on the DB.
        Prevents two sven processes running at the same time.
        Raises DatabaseLockError if already locked.
        """
        try:
            self._lock_fd = open(self.lock_path, "w")
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_fd.write(str(os.getpid()))
            self._lock_fd.flush()
            return True
        except BlockingIOError:
            raise DatabaseLockError(
                "Another Sven process is already running.\n"
                f"Lock file: {self.lock_path}\n"
                "If this is wrong, delete the lock file manually."
            )

    def release_lock(self):
        """Release the DB lock."""
        if self._lock_fd:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            self._lock_fd.close()
            self._lock_fd = None
            try:
                self.lock_path.unlink(missing_ok=True)
            except OSError:
                pass

    # ── Load ──────────────────────────────────────────────────

    def load(self):
        """Load all installed packages into memory."""
        self._cache.clear()
        self._provides.clear()
        for pkg_dir in self.db_path.iterdir():
            if not pkg_dir.is_dir():
                continue
            try:
                pkg = self._read_pkg_dir(pkg_dir)
                if pkg:
                    self._cache[pkg.name] = pkg
                    # Index provides
                    for prov in pkg.provides:
                        virt = prov.split("=")[0].split(">")[0].split("<")[0]
                        self._provides[virt.strip()] = pkg.name
            except Exception:
                # Skip corrupt entries silently
                pass
        self._loaded = True

    def _read_pkg_dir(self, pkg_dir: Path) -> Optional[Package]:
        """Read a single installed package directory."""
        desc_file = pkg_dir / "desc"
        if not desc_file.exists():
            return None

        try:
            with open(desc_file) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            raise DatabaseCorruptError(
                f"Corrupt DB entry: {pkg_dir.name}"
            )

        return Package(
            name             = data.get("name", ""),
            version          = data.get("version", ""),
            desc             = data.get("desc", ""),
            url              = data.get("url", ""),
            repo             = data.get("repo", "extra"),
            origin           = data.get("origin", "official"),
            arch             = data.get("arch", "x86_64"),
            size             = data.get("size", 0),
            isize            = data.get("isize", 0),
            deps             = data.get("deps", []),
            optdeps          = data.get("optdeps", []),
            provides         = data.get("provides", []),
            conflicts        = data.get("conflicts", []),
            replaces         = data.get("replaces", []),
            license          = data.get("license", []),
            explicit         = data.get("explicit", True),
            install_date     = data.get("install_date"),
            aur_maintainer   = data.get("aur_maintainer", ""),
            version_verified = data.get("version_verified", True),
        )

    # ── Query ─────────────────────────────────────────────────

    def get(self, name: str) -> Optional[Package]:
        """Get an installed package by name (or virtual). Returns None if not installed."""
        if not self._loaded:
            self.load()
        if name in self._cache:
            return self._cache[name]
        # Resolve as virtual
        real = self._provides.get(name)
        if real:
            return self._cache.get(real)
        return None

    def is_installed(self, name: str) -> bool:
        return self.get(name) is not None

    def has(self, name: str) -> bool:
        return self.is_installed(name)

    def list_installed(self) -> list[str]:
        return [p.name for p in self.all_packages()]

    def get_version(self, name: str) -> Optional[str]:
        pkg = self.get(name)
        return pkg.version if pkg else None

    def all_packages(self) -> list[Package]:
        if not self._loaded:
            self.load()
        return list(self._cache.values())

    def explicit_packages(self) -> list[Package]:
        """Packages explicitly installed by the user."""
        return [p for p in self.all_packages() if p.explicit]

    def auto_packages(self) -> list[Package]:
        """Packages installed automatically as dependencies."""
        return [p for p in self.all_packages() if not p.explicit]

    def aur_packages(self) -> list[Package]:
        """Packages installed from the AUR."""
        return [p for p in self.all_packages() if p.origin == "aur"]

    def orphans(self) -> list[Package]:
        """
        Auto-installed packages that nothing explicitly installed depends on.
        """
        from ..libsven import strip_constraint
        all_pkgs = self.all_packages()
        all_deps = set()

        for pkg in all_pkgs:
            for dep in pkg.deps:
                all_deps.add(strip_constraint(dep))

        return [
            p for p in self.auto_packages()
            if p.name not in all_deps
        ]

    def count_upgradable(self, sync_db=None) -> Optional[int]:
        """
        Cheap, banner-friendly estimate of how many installed packages have
        a newer version in the synced database. This is a plain version
        comparison only — no dependency graph, no AUR, no conflict checks.
        It will never be invoked for anything except a glanceable count;
        `sven upgrade` remains the real source of truth via UpgradeTransaction.
        Returns None (not 0) when no sync data exists — "no sync yet" and
        "confirmed zero upgrades" are different facts and must not collapse
        into the same misleadingly-confident number.
        """
        if sync_db is None:
            from .sync_db import SyncDB
            sync_db = SyncDB()

        from ..libsven import vercmp

        try:
            sync_db._ensure_loaded()
        except Exception:
            return None  # never synced yet — genuinely unknown, not zero

        count = 0
        for pkg in self.all_packages():
            if pkg.origin == "aur" or not pkg.version_verified:
                continue  # AUR needs network; unverified versions can't compare meaningfully
            if pkg.version.startswith(("BLFS-", "LFS-")):
                # Legacy adoption placeholder — registered before version_verified
                # existed, so it defaults True even though the string isn't a
                # real comparable version. Same exclusion graph.py's
                # _check_version applies; the two must agree or the banner's
                # estimate and the real resolver disagree on the same package.
                continue
            latest = sync_db.get(pkg.name)
            if latest is None:
                continue
            try:
                if vercmp(latest.version, pkg.version) > 0:
                    count += 1
            except Exception:
                continue
        return count

    def remove(self, name: str):
        self.unregister(name)

    def install_package(self, name: str, version: str, desc: str, url: str, files: list[str], reason: str = "depend"):
        pkg = Package(name=name, version=version, desc=desc, url=url, origin=reason)
        self.register(pkg, files, explicit=(reason == "explicit"))

    def get_files(self, name: str) -> list[str]:
        """Return list of files owned by a package."""
        pkg = self.get(name)
        if not pkg:
            raise PackageNotInstalledError(name)

        files_path = self.db_path / pkg.full_name / "files"
        if not files_path.exists():
            return []

        with open(files_path) as f:
            return [line.strip() for line in f if line.strip()]

    def disown_files(self, name: str, files) -> int:
        """
        Drop *files* from package *name*'s file list (ownership moved to
        another package). Returns how many entries were removed.
        """
        pkg = self.get(name)
        if not pkg:
            raise PackageNotInstalledError(name)
        drop = {f.lstrip("/") for f in files}
        current = self.get_files(name)
        kept = [f for f in current if f.lstrip("/") not in drop]
        removed = len(current) - len(kept)
        if removed:
            files_path = self.db_path / pkg.full_name / "files"
            self._atomic_write(files_path, "\n".join(kept))
        return removed

    def package_count(self) -> int:
        return len(self._cache)

    # ── Write ─────────────────────────────────────────────────

    def _atomic_write(self, path: Path, content: str) -> None:
        """Write to a temp file, then rename atomically (POSIX-safe)."""
        tmp = path.parent / f"{path.name}.tmp.{os.getpid()}"
        tmp.write_text(content, encoding="utf-8")
        os.replace(str(tmp), str(path))

    def register(
        self,
        pkg      : Package,
        files    : list[str],
        explicit : bool = True,
        synced_only : bool = False,
    ):
        """
        Record a package as installed.
        Creates the DB entry directory with desc + files.
        Uses atomic writes to prevent half-written entries on crash.
        """
        pkg.explicit     = explicit
        pkg.install_date = int(time.time())

        entry_dir = self.db_path / pkg.full_name
        entry_dir.mkdir(parents=True, exist_ok=True)

        # Write desc as JSON (atomic)
        desc_data = {
            "name"          : pkg.name,
            "version"       : pkg.version,
            "desc"          : pkg.desc,
            "url"           : pkg.url,
            "repo"          : pkg.repo,
            "origin"        : pkg.origin,
            "arch"          : pkg.arch,
            "size"          : pkg.size,
            "isize"         : pkg.isize,
            "deps"          : pkg.deps,
            "optdeps"       : pkg.optdeps,
            "provides"      : pkg.provides,
            "conflicts"     : pkg.conflicts,
            "replaces"      : pkg.replaces,
            "license"       : pkg.license,
            "explicit"      : pkg.explicit,
            "install_date"  : pkg.install_date,
            "aur_maintainer": pkg.aur_maintainer,
            "version_verified": pkg.version_verified,
            "sven_synced_only": synced_only,  # True = pacman-installed, not removable by Sven
        }

        self._atomic_write(entry_dir / "desc", json.dumps(desc_data, indent=2))

        # Write files list (atomic)
        self._atomic_write(entry_dir / "files", "\n".join(files))

        # Update in-memory cache
        self._cache[pkg.name] = pkg

    def unregister(self, name: str):
        """
        Remove a package from the DB.
        Called during removal AFTER files are deleted.
        """
        pkg = self.get(name)
        if not pkg:
            raise PackageNotInstalledError(name)

        entry_dir = self.db_path / pkg.full_name

        # Remove desc and files
        for f in ("desc", "files"):
            p = entry_dir / f
            if p.exists():
                p.unlink()

        # Remove directory
        try:
            entry_dir.rmdir()
        except OSError:
            pass  # not empty for some reason — leave it

        # Remove from cache
        self._cache.pop(name, None)

    def update_version(self, pkg: Package, files: list[str]):
        """
        Update an existing package to a new version.
        Called during upgrade — removes old entry, registers new.
        """
        old_pkg = self.get(pkg.name)
        if old_pkg:
            # Remove old entry dir
            old_dir = self.db_path / old_pkg.full_name
            for f in ("desc", "files"):
                p = old_dir / f
                if p.exists():
                    p.unlink()
            try:
                old_dir.rmdir()
            except OSError:
                pass

        # Register new version — preserve explicit flag
        explicit = old_pkg.explicit if old_pkg else True
        self.register(pkg, files, explicit=explicit)
