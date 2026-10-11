# ============================================================
#  Sven — Seven OS Package Manager
#  HANS TECH © 2024 — GPL v3
#  sven/transaction.py — The Action Orchestrator
# ============================================================
#
#  Wires up all Phase 0-5 modules into a cohesive, atomic
#  operation. Wraps everything in Rollback protection.
# ============================================================

import os
import time
import shutil
from pathlib import Path
from datetime import datetime

from .config import get_config
from .exceptions import SvenError, RollbackFailedError, ProtectedPackageError, ChecksumMismatchError

from .db.models import Package
from .db.local_db import LocalDB
from .db.sync_db import SyncDB
from .db.aur_db import AURDB

from .resolver.graph import DependencyGraph
from .resolver.sorter import sort_dependencies
from .resolver.conflict import check_conflicts
from .resolver.compat import check_binary_compatibility
from .resolver.systemd_filter import filter_systemd_packages
from .resolver.file_conflict import check_file_conflicts

from .downloader.mirror import MirrorManager
from .downloader.fetcher import Fetcher
from .downloader.gpg import GPGVerifier
from .downloader.checksum import verify_checksum
from .downloader.pkgbuild_fetcher import PKGBUILDFetcher


from .builder.pkgbuild import parse_pkgbuild
from .builder.makepkg import build_aur_packages, run_makepkg
from .builder.aur_cache import AURCache

from .installer.extractor import Extractor
from .installer.hooks import HookRunner, run_auto_hooks
from .installer.lib_checker import LibChecker
from .installer.rollback import RollbackManager

from .ui.output import print_section, print_info, print_step, print_success
from .ui.graph_render import render_dependency_tree

from . import constants as C
LOG_DIR = C.LOG_DIR
LOG_FILE = C.LOG_MAIN

class Transaction:
    """
    Base class for all Sven operations.
    Ensures absolute atomic safety by wrapping the action in DB locks
    and Rollback snapshots.
    """

    def __init__(self):
        self.config = get_config()
        self.local_db = LocalDB()
        self.rollback = RollbackManager()
        self.verbose = False
        
        # Ensure log dir exists
        log_path = Path(self.config.rooted(LOG_DIR))
        if not log_path.exists():
            log_path.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        packages: list[str],
        force_protected: bool = False,
        _use_resolved: bool = False,
        force_reinstall: bool = False,
    ) -> bool:
        """
        Public entry point. 
        Acquires lock, creates snapshot, tries operation.
        If it throws, rolls back automatically.
        """
        start_time = time.time()
        success = False
        snapshot_id = None
        error_msg = ""
        
        # 1. Acquire global database lock
        if not self.local_db.acquire_lock():
            print("   ⚠ Error: Cannot acquire database lock! Is another instance of Sven running?")
            return False

        try:
            # 2. Before we even touch anything, create a pre-tx snapshot
            # We don't know the exact install list yet, so snapshot depends on tx type
            snapshot_pkgs = self._get_snapshot_packages(packages)
            snapshot_id = self.rollback.create_snapshot(snapshot_pkgs)

            # 3. Fire the implementation
            if self.verbose:
                print(f"   [DEBUG] Starting core execution for: {', '.join(packages) if packages else 'all'}")
                print(f"   [DEBUG] Snapshot ID: {snapshot_id}")
            self._execute_core(
                packages,
                force_protected=force_protected,
                _use_resolved=_use_resolved,
                force_reinstall=force_reinstall,
            )
            success = True

        except Exception as e:
            # 4. Catastrophic or planned failure → Auto Rollback
            success = False
            error_msg = str(e)

            # Special formatting for ProtectedPackageError
            if isinstance(e, ProtectedPackageError):
                print(f"\n{e}\n")
            else:
                try:
                    from .ui.output import print_error_box
                    print_error_box(
                        str(e),
                        title="Install failed — restoring the pre-transaction snapshot",
                        show_log_hint=False,
                    )
                except Exception:
                    print(f"\n   Install failed — restoring the pre-transaction snapshot")
                    print(f"   Cause: {e}")
            
            if snapshot_id:
                try:
                    self.rollback.restore(snapshot_id)
                    print("   ✓ System successfully reverted.")
                except Exception as rollback_e:
                    print(
                        "   [CRITICAL] Rollback did not complete successfully: "
                        f"{rollback_e}"
                    )
                    print(
                        "   [CRITICAL] The system may be inconsistent — "
                        "stop and seek help before rebooting or upgrading."
                    )

        finally:
            # 5. Release lock & Log
            self.local_db.release_lock()
            duration = round(time.time() - start_time, 2)
            self._log_transaction(packages, success, duration, error_msg)

        return success

    def _execute_core(
        self,
        packages: list[str],
        force_protected: bool = False,
        _use_resolved: bool = False,
        force_reinstall: bool = False,
    ):
        """Implemented by child classes."""
        raise NotImplementedError

    def _get_snapshot_packages(self, packages: list[str]) -> list[str]:
        """Implemented by child classes. Return pkgs to backup in snapshot."""
        return packages

    def _log_transaction(self, packages: list[str], success: bool, duration: float, error_msg: str):
        """Append to system log."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "SUCCESS" if success else f"FAIL ({error_msg})"
        pkg_str = " ".join(packages) if packages else "ALL"
        op = self.__class__.__name__.replace("Transaction", "").upper()

        log_line = f"[{timestamp}] [{op}] pkgs:[{pkg_str}] status:[{status}] duration:[{duration}s]\n"
        
        log_path = Path(self.config.rooted(LOG_FILE))
        try:
            with open(log_path, "a") as f:
                f.write(log_line)
        except OSError:
            pass

    def _handle_scary_prompt(self, detected: list[str]):
        """Show the extra scary warning for protected packages."""
        print(f"\n   \033[91m⚠  WARNING: Protected packages detected: {', '.join(detected)}\033[0m")
        print("   Overriding protection for core LFS packages is DANGEROUS.")
        print("   If you proceed, your system may become UNBOOTABLE.")
        print("")
        import sys
        reply = input("   Type 'YES I KNOW' to continue: ")
        if reply != "YES I KNOW":
            print("   Aborted by user.")
            sys.exit(1)
        
        # Log override to sven.log
        log_path = Path(self.config.rooted(C.LOG_MAIN))
        try:
            with open(log_path, "a") as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [OVERRIDE] force_protected used for: {', '.join(detected)}\n")
        except: pass



class InstallTransaction(Transaction):
    """
    Handles resolving, downloading, building, and installing packages.
    """
    def __init__(self, explicit: bool = True, verbose: bool = False):
        super().__init__()
        self.explicit = explicit
        self.verbose = verbose

        self.sync_db = SyncDB()
        self.aur_db = AURDB()

    def resolve(
        self,
        targets: list[str],
        force_protected: bool = False,
        force_reinstall: bool = False,
        version: str = None,
    ) -> list:
        """
        Phase 1 only: resolve deps and return the filtered install order.
        This lets the CLI show the user what they're getting BEFORE confirming.
        Returns an empty list if nothing to install.
        """
        if not targets:
            return []

        graph = DependencyGraph(self.sync_db, self.aur_db, self.local_db)
        for target in targets:
            if version:
                graph.add_package(f"{target}={version}")
            else:
                graph.add_package(target)

        install_order = sort_dependencies(graph.nodes, graph.edges)
        graph.warn_placeholder_packages()

        installed = self.local_db.list_installed()
        if not force_reinstall:
            final_order = []
            for p in install_order:
                if p.name not in installed:
                    final_order.append(p)
                else:
                    local_pkg = self.local_db.get(p.name)
                    if local_pkg and local_pkg.version != p.version:
                        final_order.append(p)
            install_order = final_order

        if not install_order:
            return []

        filtered_pkgs, _ = filter_systemd_packages(
            install_order,
            self.config.init_system,
            strict=False,
        )
        return filtered_pkgs

    def execute_resolved(
        self,
        resolved_pkgs: list,
        force_protected: bool = False,
        force_reinstall: bool = False,
        install_targets: list[str] | None = None,
    ) -> bool:
        """
        Execute install phases 2-6 using a pre-resolved package list.
        Called after the user confirms.
        """
        if not resolved_pkgs:
            print("Nothing to install.")
            return True
        
        # Save the resolved list and call _execute_resolved_core inside the transaction wrapper
        self._resolved_pkgs = resolved_pkgs
        self._install_target_names = frozenset(install_targets or [])
        return self.execute(
            [],
            force_protected=force_protected,
            _use_resolved=True,
            force_reinstall=force_reinstall,
        )
        

    def _execute_core(
        self,
        targets: list[str],
        force_protected: bool = False,
        _use_resolved: bool = False,
        force_reinstall: bool = False,
    ):
        installed = self.local_db.list_installed()

        # If we have pre-resolved packages, skip resolution
        if _use_resolved and hasattr(self, '_resolved_pkgs'):
            filtered_pkgs = self._resolved_pkgs
            install_order_names = [p.name for p in filtered_pkgs]
        else:
            if not targets:
                print("Nothing to install.")
                return

            print()
            print_section("Install · 1/6 · Resolving dependencies")
            graph = DependencyGraph(self.sync_db, self.aur_db, self.local_db)

            for target in targets:
                graph.add_package(target)
            
            install_order = sort_dependencies(graph.nodes, graph.edges)
            graph.warn_placeholder_packages()

            if not force_reinstall:
                final_order = []
                for p in install_order:
                    if p.name not in installed:
                        final_order.append(p)
                    else:
                        local_pkg = self.local_db.get(p.name)
                        if local_pkg and local_pkg.version != p.version:
                            final_order.append(p)
                install_order = final_order

            if not install_order:
                print("Target is already up to date.")
                return

            filtered_pkgs, _ = filter_systemd_packages(
                install_order,
                self.config.init_system,
                strict=False,
            )
            install_order_names = [p.name for p in filtered_pkgs]

            if not filtered_pkgs:
                print("Target is already up to date or blocked.")
                return

        explicit_names = (
            self._install_target_names
            if _use_resolved and hasattr(self, "_install_target_names")
            else frozenset(targets)
        )

        if self.verbose or len(install_order_names) <= 14:
            print_info(f"Dependency order: {' → '.join(install_order_names)}")
        else:
            print_info(
                f"Dependency order: {len(install_order_names)} packages "
                "(use --verbose to print the full list)"
            )

        # Package-level conflicts only need declared metadata (conflicts/
        # provides/replaces) and the local DB — nothing downloaded yet at
        # this point. Check now, before spending any time or bandwidth on
        # a transaction that's going to fail anyway. File-level conflicts
        # and ABI checks genuinely need the downloaded archive, so those
        # stay in step 4 where they already are.
        check_conflicts(filtered_pkgs, self.local_db)
        print()

        # Separate official vs AUR vs Build targets
        to_download = []
        to_build = []

        for pkg in filtered_pkgs:
            if pkg.origin == "aur":
                to_build.append(pkg)
            else:
                # All non-aur are considered official/sync for this phase
                to_download.append(pkg)

        print_section("Install · 2/6 · Fetching packages")

        # Download Official Packages
        downloaded_paths = {}
        if not to_download:
            print_info(
                "No packages to download from mirrors (using cache and/or local builds only)."
            )
        if to_download:
            manager = MirrorManager()
            if self.verbose:
                print_info(f"Primary mirror: {manager.current}")
                print_step("Parallel downloads with live progress; mirror failover is automatic.")
                print_info(f"Downloading {len(to_download)} package(s)...")
                for pkg in to_download:
                    print(f"   • {pkg.name:<18} {pkg.filename} ({pkg.size/1024/1024:.1f} MiB)")
                    if self.verbose:
                        print(f"     [DEBUG] Repo: {pkg.repo} | Hash: {pkg.csum[:32]}...")
            else:
                print_info(f"Downloading {len(to_download)} package(s)...")
            fetcher = Fetcher(manager, verbose=self.verbose)
            downloaded_paths = fetcher.download_packages(
                to_download, verbose=self.verbose
            )
                 
            # GPG Verification of signatures
            if self.verbose:
                print_info("Verifying GPG signatures...")
            gpg = GPGVerifier()
            for pkg in to_download:
                path = downloaded_paths.get(pkg.name)
                if path:
                    if self.verbose:
                        print_step(f"Verifying {pkg.filename}...")
                    gpg.verify(path)
                    if self.verbose:
                        print(f"   ✓ GPG signature verified: {pkg.filename}")
            if self.verbose:
                print_success("All GPG signatures verified successfully")

        # Build AUR Packages
        built_paths = {}
        if to_build:
            pkgbuild_fetcher = PKGBUILDFetcher()
            aur_cache = AURCache()
            
            build_queue = []
            for pkg in to_build:
                pkg_dir = pkgbuild_fetcher.fetch_aur(pkg.name)
                
                # Check cache first
                cached = aur_cache.check_before_build(pkg.name, pkg.version)
                if cached and not force_reinstall:
                    built_paths[pkg.name] = cached
                else:
                    build_queue.append({"name": pkg.name, "dir": pkg_dir})
            
            if build_queue:
                print()
                print_section("Install · 3/6 · Compiling AUR packages")
                if self.verbose:
                    print_step("Build output from makepkg follows below.")
                results = build_aur_packages(build_queue, interactive=True)
                built_paths.update(results)
                
                # Store new builds in cache
                for pkg in to_build:
                    if pkg.name in results:
                        aur_cache.store(pkg.name, pkg.version, results[pkg.name])

        # Conflict Checking & Safety
        merged_paths = {**downloaded_paths, **built_paths}

        print()
        print_section("Install · 4/6 · Safety checks")
        if self.verbose:
            print_step(
                "Checking package conflicts, file overlaps on disk, and library hints."
            )
            print_info(f"Running checks on {len(filtered_pkgs)} package(s)...")

        # Package-level conflicts were already checked before downloading
        # (see above) — no reason to check again here.
        
        # File-level conflicts
        if self.verbose:
            print_step("Checking file-level conflicts...")
        takeovers: dict[tuple[str, str], set[str]] = {}
        for pkg in filtered_pkgs:
            archive = merged_paths.get(pkg.name)
            if archive:
                if self.verbose:
                    print(f"   • Checking {pkg.filename}...")
                found = check_file_conflicts(
                    pkg, archive, self.local_db, force=False,
                    allow_split_takeover=True,
                    protected_packages=self.config.protected_packages,
                    force_protected=force_protected,
                )
                for c in found:
                    if c.get("takeover"):
                        takeovers.setdefault(
                            (c["owner"], c["new_pkg"]), set()
                        ).add(c["file"])
        if takeovers:
            for (owner, new_pkg), files in takeovers.items():
                print_info(
                    f"{new_pkg} is a split of installed '{owner}': "
                    f"taking over {len(files)} file(s)"
                )
        elif self.verbose:
            print_success("No file conflicts detected")
                
        # Library Checks & ABI compatibility
        if self.verbose:
            print_step("Checking library compatibility...")
        lib_chk = LibChecker()
        from .resolver.compat import check_package_abi
        for pkg_name, archive in merged_paths.items():
            # In real system, we'd read requires from archive .PKGINFO
            # Here we skip deep mock lookup for brevity
            pass
            
            # Deep ABI GLIBC requirements vs Host Check
            abi_res = check_package_abi(archive)
            if not abi_res["compatible"]:
                error_details = "\n".join(abi_res["details"])
                raise SvenError(f"Package {pkg_name} is practically incompatible with host glibc:\n{error_details}")
        if self.verbose:
            print_success("All library compatibility checks passed")

        print()
        print_section("Install · 5/6 · Extracting onto system")
        if self.verbose:
            print_step("Running per-package install hooks before and after files land.")
            print_info(f"Extracting {len(filtered_pkgs)} package(s)...")
        ext = Extractor(verbose=self.verbose)
        
        all_extracted_files = []
        
        for i, pkg in enumerate(filtered_pkgs, 1):
            pkg_name = pkg.name
            if pkg_name not in merged_paths:
                continue
                 
            archive = merged_paths[pkg_name]
            
            if self.verbose:
                print(f"   [{i}/{len(filtered_pkgs)}] Extracting {pkg.filename}...")
            
            # Pre hooks
            hr = HookRunner(pkg.name, Path(archive).with_name(".INSTALL").as_posix())
            hr.run_phase("pre_install", pkg.version)

            # Extract!
            files_extracted = ext.extract(archive, pkg=pkg, reason=0 if (self.explicit and pkg.name in explicit_names) else 1)
            all_extracted_files.extend(files_extracted)
            
            if self.verbose:
                print(f"   ✓ Extracted {len(files_extracted)} files")

            # Register
            self.local_db.register(
                pkg,
                files_extracted,
                explicit=(self.explicit and pkg.name in explicit_names),
            )
            
            if self.verbose:
                print(f"   ✓ Registered {pkg.name} in database")

            # Post hooks
            hr.run_phase("post_install", pkg.version)

        # Split-package takeovers: the old owner no longer owns those files
        # (so removing it later won't delete files the new package needs).
        for (owner, _new_pkg), files in takeovers.items():
            if self.local_db.has(owner):
                self.local_db.disown_files(owner, files)

        print()
        print_section("Install · 6/6 · Global hooks")
        if self.verbose:
            print_step("Updating caches, databases, and other system-wide post-install tasks.")
            print_info("Running system-wide post-install hooks...")
            
        # Run Arch ALPM Hooks
        from .installer.alpm_hooks import ALPMHookEngine
        hook_engine = ALPMHookEngine()
        hook_engine.evaluate_and_run(all_extracted_files)
        
        run_auto_hooks()
        if self.verbose:
            print_success("All system hooks completed successfully")

        print()
        print_success("Transaction successfully sealed.")


class RemoveTransaction(Transaction):
    """
    Handles safely removing packages and cleaning DB.
    """
    def _execute_core(
        self,
        targets: list[str],
        force_protected: bool = False,
        _use_resolved: bool = False,
        force_reinstall: bool = False,
    ):
        if not targets:
            return

        # Check protection
        protected_list = self.config.protected_packages
        if not force_protected:
            for pkg_name in targets:
                if pkg_name in protected_list:
                    raise ProtectedPackageError(pkg_name)

        print("\n   [Remove] Preparing deletion...")
        
        for pkg_name in targets:
            if not self.local_db.has(pkg_name):
                print(f"Target {pkg_name} is not installed.")
                continue
                
            # TODO: Add reverse dependency logic if required
            
            # Run pre_remove
            hr = HookRunner(pkg_name, f"/var/lib/sven/local/{pkg_name}/.INSTALL")
            hr.run_phase("pre_remove", "latest")
            
            files = self.local_db.get_files(pkg_name)
            for f in files:
                p = Path(self.config.rooted(f))
                if p.exists() and p.is_file():
                    p.unlink()
            
            self.local_db.remove(pkg_name)
            
            hr.run_phase("post_remove", "latest")

        run_auto_hooks()
        print("\n   ★ Transaction successfully sealed.")


class UpgradeTransaction(InstallTransaction):
    """
    Upgrades installed system.
    """
    def resolve(
        self,
        targets: list[str] = None,
        force_protected: bool = False,
        force_reinstall: bool = False,
        version: str = None,
        skip_aur: bool = False,
    ) -> list:
        print("\n   [Upgrade] Synchronizing local catalog with mirrors...")
        
        installed = self.local_db.list_installed()
        to_upgrade = []
        aur_check_list = []
        
        for pkg_name in installed:
            if targets and pkg_name not in targets:
                continue
                
            local_pkg = self.local_db.get(pkg_name)
            if not local_pkg:
                continue

            remote_pkg = self.sync_db.get(pkg_name)
            
            if remote_pkg:
                if remote_pkg.version != local_pkg.version:
                    to_upgrade.append(pkg_name)
            else:
                aur_check_list.append(pkg_name)

        self.skipped_aur_count = 0
        if aur_check_list:
            if skip_aur:
                # Honest about what got skipped, not just silent — these
                # packages are simply not checked at all this run, so an
                # available AUR update for them won't be reflected below.
                self.skipped_aur_count = len(aur_check_list)
            else:
                print("   [Upgrade] Checking AUR for updates...")
                aur_pkgs = self.aur_db.info_multi(aur_check_list)
                for remote_pkg in aur_pkgs:
                    local_pkg = self.local_db.get(remote_pkg.name)
                    if local_pkg and remote_pkg.version != local_pkg.version:
                        to_upgrade.append(remote_pkg.name)
                
        if not to_upgrade:
            return []
        
        # Hand off the diff to InstallTransaction.resolve to build the dependency graph!
        return super().resolve(
            to_upgrade,
            force_protected=force_protected,
            force_reinstall=force_reinstall,
            version=version,
        )
