# ============================================================
#  Sven — Seven OS Package Manager
#  HANS TECH © 2024 — GPL v3
#  constants.py — global constants, paths, URLs
# ============================================================

import os
import sys

# ── Dynamic Root parsing ─────────────────────────────────────
_ROOT = ""
try:
    if "--root" in sys.argv:
        _ROOT = sys.argv[sys.argv.index("--root") + 1].rstrip("/")
    elif "-r" in sys.argv:
        _ROOT = sys.argv[sys.argv.index("-r") + 1].rstrip("/")
except Exception:
    pass

# ── Version ──────────────────────────────────────────────────
VERSION       = "2.1.2"
CODENAME      = "Forge"

# ── Identity ─────────────────────────────────────────────────
APP_NAME      = "sven"
BRAND         = "HANS TECH"
OS_NAME       = "Seven OS"
GITHUB        = "https://github.com/haroldmth/sven"

# ── Install Root (overridable via --root flag) ───────────────
DEFAULT_ROOT  = _ROOT or "/"

# ── Sven DB Paths ────────────────────────────────────────────
DB_BASE       = f"{_ROOT}/var/lib/sven"
DB_INSTALLED  = f"{DB_BASE}/installed"
DB_SYNC       = f"{DB_BASE}/sync"
DB_AUR_CACHE  = f"{DB_BASE}/aur_cache"
DB_SNAPSHOTS  = f"{DB_BASE}/snapshots"
DB_LOCK       = f"{DB_BASE}/lock"
PACMAN_LOCK   = f"{_ROOT}/var/lib/pacman/db.lck"

# ── Cache ────────────────────────────────────────────────────
CACHE_BASE    = f"{_ROOT}/var/cache/sven"
CACHE_PKGS    = f"{CACHE_BASE}/pkgs"
CACHE_AUR     = f"{CACHE_BASE}/aur"

# ── Logging ──────────────────────────────────────────────────
LOG_DIR       = f"{_ROOT}/var/log/sven"
LOG_MAIN      = f"{LOG_DIR}/sven.log"
LOG_HOOKS     = f"{LOG_DIR}/hooks.log"

# ── Config ───────────────────────────────────────────────────
CONFIG_DIR    = f"{_ROOT}/etc/sven"
CONFIG_FILE   = f"{CONFIG_DIR}/sven.conf"
INITSCRIPTS   = f"{CONFIG_DIR}/initscripts"

# ── Temp / Build ─────────────────────────────────────────────
TMP_BASE      = f"{_ROOT}/tmp/sven"
TMP_AUR       = f"{TMP_BASE}/aur"
TMP_BUILD     = f"{TMP_BASE}/build"

# ── Arch Repos ───────────────────────────────────────────────
ARCH_REPOS    = ["core", "extra", "multilib"]
ARCH_ARCH     = "x86_64"

# ── Default Mirror ───────────────────────────────────────────
DEFAULT_MIRROR         = "https://mirror.rackspace.com/archlinux"
ARCH_MIRROR_STATUS_URL = "https://archlinux.org/mirrors/status/json/"

# ── Mirror DB URL Template ───────────────────────────────────
# Usage: MIRROR_DB_URL.format(mirror=..., repo=..., arch=...)
MIRROR_DB_URL  = "{mirror}/{repo}/os/{arch}/{repo}.db"
MIRROR_PKG_URL = "{mirror}/{repo}/os/{arch}/{filename}"

# ── AUR ──────────────────────────────────────────────────────
AUR_RPC_URL    = "https://aur.archlinux.org/rpc/v5"
AUR_CLONE_URL  = "https://aur.archlinux.org/{pkg}.git"
AUR_CACHE_TTL  = 3600   # seconds before AUR cache expires

# ── Arch GitLab (official PKGBUILDs for source builds) ───────
ARCH_GITLAB_URL = "https://gitlab.archlinux.org/archlinux/packaging/packages"

# ── Package Format ───────────────────────────────────────────
PKG_EXTENSIONS = [".pkg.tar.zst", ".sven"]
PKGINFO_FILE   = ".PKGINFO"
INSTALL_FILE   = ".INSTALL"
MTREE_FILE     = ".MTREE"

# ── Supported Init Systems ───────────────────────────────────
# Seven OS uses SysVinit/OpenRC, so we filter systemd deps.
INIT_SYSTEMD  = "systemd"
INIT_SYSVINIT = "sysvinit"
INIT_OPENRC   = "openrc"
SUPPORTED_INIT = [INIT_SYSTEMD, INIT_SYSVINIT, INIT_OPENRC]

# ── DB Freshness ─────────────────────────────────────────────
DB_MAX_AGE_SECONDS = 86400   # 24 hours before stale warning

# ── Download ─────────────────────────────────────────────────
PARALLEL_DOWNLOADS  = 8
DOWNLOAD_CHUNK_SIZE = 4096   # smaller chunks handled better on lossy links
DOWNLOAD_TIMEOUT    = 120    # seconds
MIRROR_BENCH_COUNT  = 5      # mirrors to benchmark

# ── Security ─────────────────────────────────────────────────
GPG_KEYRING    = "/etc/pacman.d/gnupg"   # reuse Arch keyring if present
MIN_SIG_LEVEL  = "required"

# ── Hook Scanner — dangerous patterns ────────────────────────
DANGEROUS_HOOK_PATTERNS = [
    "curl",
    "wget",
    "bash -c",
    "sh -c",
    "eval",
    "exec",
    "nc ",
    "ncat",
    "/dev/tcp",
    "base64 -d",
    "python -c",
    "perl -e",
    "ruby -e",
    "dd if",
    "mkfifo",
    "rm -rf /",
]
