# Updates & Architecture Notes

This document provides a high-level changelog and critical technical notes regarding major releases of Sven.

## v2.1.2
* **File-conflict fix for LFS systems**: shared directories (e.g. `usr/include/systemd`) are no longer treated as file conflicts, and Arch split packages (`util-linux-libs`, `systemd-libs`, `gcc-libs`) can take over files from their adopted monolithic parent. Taking over from a protected package requires `--force-protected`. All conflicts are now counted instead of only the first.
* **CI/CD**: tests on every push/PR; tagged releases are gated on tests and a version check, built on an older glibc, and published to GitHub Releases and (optionally) the AUR.
* **AUR**: fixed asset name, real checksums, and hook files in the published package.

## v1.0.0 (The Genesis Release)
* **Initial Release**: Established the core framework for Seven OS SysVinit operations.
* **Rollback Engine**: Fully implemented `snapshot` capability.
* **AUR Support**: Fully autonomous extraction, cloning, and `makepkg` routines integrated natively into the `install` workflow.
* **Double-Check Algorithm**: Added intelligent HTML/corrupted chunk interception, saving hours of bandwidth by catching corrupt mirrors instantly.
* **Self-Update Engine**: Implemented native pull logic to synchronize /usr/bin/sven with the GitHub master releases.

## Future Roadmaps (v1.x -> v2.0)
* **Multithreaded Build Farm**: Enabling Sven to build multiple disconnected AUR packages efficiently in parallel.
* **TUI Interface**: Transitioning from a purely CLI-stdout interface into a full interactive `curses` TUI for managing the LocalDB.
