# ============================================================
#  Sven — Seven OS Package Manager
#  HANS TECH © 2024 — GPL v3
#  exceptions.py — all custom exception types
# ============================================================


# ── Base ─────────────────────────────────────────────────────

class SvenError(Exception):
    """Base exception for all Sven errors."""
    pass


# ── Database ─────────────────────────────────────────────────

class DatabaseError(SvenError):
    """Generic database error."""
    pass

class DatabaseCorruptError(DatabaseError):
    """Sven local DB is corrupt or incomplete."""
    pass

class DatabaseStaleError(DatabaseError):
    """Sync DB is too old and needs refreshing."""
    pass

class DatabaseLockError(DatabaseError):
    """Another Sven process is running."""
    pass


# ── Package ──────────────────────────────────────────────────

class PackageError(SvenError):
    """Generic package error."""
    pass

class PackageNotFoundError(PackageError):
    """Package not found in official repos or AUR."""
    def __init__(self, pkg_name: str):
        self.pkg_name = pkg_name
        super().__init__(f"Package not found: {pkg_name}")

class PackageAlreadyInstalledError(PackageError):
    """Package is already installed."""
    def __init__(self, pkg_name: str, version: str):
        self.pkg_name = pkg_name
        self.version  = version
        super().__init__(f"{pkg_name} {version} is already installed")

class PackageNotInstalledError(PackageError):
    """Package is not installed."""
    def __init__(self, pkg_name: str):
        self.pkg_name = pkg_name
        super().__init__(f"{pkg_name} is not installed")


# ── Dependency ───────────────────────────────────────────────

class DependencyError(SvenError):
    """Generic dependency error."""
    pass

class DependencyNotFoundError(DependencyError):
    """A required dependency could not be resolved."""
    def __init__(self, dep_name: str, required_by: str):
        self.dep_name    = dep_name
        self.required_by = required_by
        super().__init__(
            f"Dependency '{dep_name}' not found (required by {required_by})"
        )

class DependencyConflictError(DependencyError):
    """Two packages conflict with each other."""
    def __init__(self, pkg_a: str, pkg_b: str):
        self.pkg_a = pkg_a
        self.pkg_b = pkg_b
        super().__init__(f"Conflict: {pkg_a} conflicts with {pkg_b}")

class CircularDependencyError(DependencyError):
    """Circular dependency detected in the graph."""
    def __init__(self, cycle: list):
        self.cycle = cycle
        chain = " → ".join(cycle)
        super().__init__(f"Circular dependency detected: {chain}")

class VersionConstraintError(DependencyError):
    """A version constraint could not be satisfied."""
    def __init__(self, pkg: str, required: str, found: str):
        self.pkg      = pkg
        self.required = required
        self.found    = found
        super().__init__(
            f"Version mismatch for {pkg}: need {required}, found {found}"
        )


# ── Download ─────────────────────────────────────────────────

class DownloadError(SvenError):
    """Generic download error."""
    pass

class MirrorError(DownloadError):
    """All mirrors failed."""
    pass

class MirrorTimeoutError(DownloadError):
    """Mirror timed out."""
    def __init__(self, mirror: str):
        self.mirror = mirror
        super().__init__(f"Mirror timed out: {mirror}")

class ChecksumMismatchError(DownloadError):
    """SHA256 checksum does not match."""
    def __init__(self, filename: str, expected: str, actual: str):
        self.filename = filename
        self.expected = expected
        self.actual   = actual
        super().__init__(f"Checksum mismatch for {filename}\n         Expected: {expected}\n         Actual:   {actual}")

class SignatureError(DownloadError):
    """GPG signature verification failed."""
    def __init__(self, filename: str):
        self.filename = filename
        super().__init__(
            f"GPG signature verification FAILED: {filename}\n"
            f"Package may be tampered with. Aborting."
        )


# ── AUR / Build ──────────────────────────────────────────────

class AURError(SvenError):
    """Generic AUR error."""
    pass

class AURPackageNotFoundError(AURError):
    """Package not found on AUR."""
    def __init__(self, pkg_name: str):
        self.pkg_name = pkg_name
        super().__init__(f"AUR package not found: {pkg_name}")

class BuildError(AURError):
    """makepkg build failed."""
    def __init__(self, pkg_name: str, reason: str = ""):
        self.pkg_name = pkg_name
        self.reason   = reason
        super().__init__(
            f"Build failed for {pkg_name}"
            + (f": {reason}" if reason else "")
        )

class PKGBUILDError(AURError):
    """PKGBUILD could not be parsed."""
    def __init__(self, pkg_name: str):
        self.pkg_name = pkg_name
        super().__init__(f"Could not parse PKGBUILD for {pkg_name}")

class RootBuildError(AURError):
    """Attempted to run makepkg as root."""
    def __init__(self):
        super().__init__(
            "makepkg must never run as root.\n"
            "Sven will not proceed. This is a safety restriction."
        )


# ── Install ──────────────────────────────────────────────────

class InstallError(SvenError):
    """Generic install error."""
    pass

class FileConflictError(InstallError):
    """A file already exists on disk owned by another package."""
    def __init__(self, filepath: str, owner: str):
        self.filepath = filepath
        self.owner    = owner
        super().__init__(
            f"File conflict: {filepath} already owned by {owner}"
        )

class MissingLibraryError(InstallError):
    """A required shared library is missing from the system."""
    def __init__(self, lib: str, required_by: str):
        self.lib         = lib
        self.required_by = required_by
        super().__init__(
            f"Missing library: {lib} (required by {required_by})"
        )

class ExtractionError(InstallError):
    """Failed to extract a package archive."""
    def __init__(self, filename: str, reason: str = ""):
        self.filename = filename
        super().__init__(
            f"Extraction failed: {filename}"
            + (f" — {reason}" if reason else "")
        )


# ── Hooks ────────────────────────────────────────────────────

class HookError(SvenError):
    """Generic hook error."""
    pass

class DangerousHookError(HookError):
    """Hook contains a dangerous pattern."""
    def __init__(self, pkg_name: str, pattern: str):
        self.pkg_name = pkg_name
        self.pattern  = pattern
        super().__init__(
            f"Dangerous pattern in {pkg_name} hook: '{pattern}'"
        )

class HookTranslationError(HookError):
    """systemd hook could not be translated to SysVinit."""
    def __init__(self, hook_line: str):
        self.hook_line = hook_line
        super().__init__(f"Cannot translate hook: {hook_line}")


# ── Rollback ─────────────────────────────────────────────────

class RollbackError(SvenError):
    """Generic rollback error."""
    pass

class SnapshotNotFoundError(RollbackError):
    """Snapshot ID does not exist."""
    def __init__(self, snapshot_id: str):
        self.snapshot_id = snapshot_id
        super().__init__(f"Snapshot not found: {snapshot_id}")

class RollbackFailedError(RollbackError):
    """Rollback itself failed partway through."""
    def __init__(self, reason: str):
        super().__init__(f"Rollback failed: {reason}")


# ── Config ───────────────────────────────────────────────────

class ConfigError(SvenError):
    """Generic config error."""
    pass

class ConfigNotFoundError(ConfigError):
    """Config file does not exist."""
    def __init__(self, path: str):
        self.path = path
        super().__init__(f"Config file not found: {path}")

class InvalidConfigError(ConfigError):
    """Config file has invalid values."""
    def __init__(self, key: str, value: str):
        self.key   = key
        self.value = value
        super().__init__(f"Invalid config value: {key} = {value}")


# ── Migration ────────────────────────────────────────────────

class MigrationError(SvenError):
    """Init system migration error."""
    pass


# ── Hardening ────────────────────────────────────────────────

class FileConflictError(SvenError):
    """A file is already owned by another package."""
    def __init__(self, filename: str, owner_pkg: str, new_pkg: str, total: int = 1):
        self.filename  = filename
        self.owner_pkg = owner_pkg
        self.new_pkg   = new_pkg
        self.total     = total
        more = f" (+{total - 1} more conflicting file(s))" if total > 1 else ""
        super().__init__(
            f"File conflict: {filename} is owned by '{owner_pkg}', "
            f"cannot be overwritten by '{new_pkg}'{more}"
        )

class SystemdDependencyError(SvenError):
    """Package requires systemd components unavailable on this init system."""
    def __init__(self, pkg: str, systemd_deps: list):
        self.pkg          = pkg
        self.systemd_deps = systemd_deps
        deps_str = ", ".join(systemd_deps)
        super().__init__(
            f"Package '{pkg}' requires systemd components: {deps_str}. "
            f"Seven OS uses SysVinit — install from source or find an alternative."
        )

class ABIIncompatibleError(SvenError):
    """Binary package requires a newer glibc than the host provides."""
    def __init__(self, pkg: str, required_glibc: str, host_glibc: str):
        self.pkg             = pkg
        self.required_glibc  = required_glibc
        self.host_glibc      = host_glibc
        super().__init__(
            f"ABI incompatible: '{pkg}' requires glibc >= {required_glibc}, "
            + f"but host has {host_glibc}. Build from source instead."
        )


class ProtectedPackageError(SvenError):
    """Attempted to manage a protected LFS package."""
    def __init__(self, pkg_name: str):
        self.pkg_name = pkg_name
        super().__init__(
            f"✗  {pkg_name} is a protected LFS package.\n"
            f"   Sven will not manage this package automatically.\n"
            f"   To override: sven install {pkg_name} --force-protected\n"
            f"   WARNING: This may break your system."
        )

