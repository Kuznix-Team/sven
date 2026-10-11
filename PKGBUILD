# Maintainer: HANS TECH <open-source@hanstech.dev>
pkgname=sven-bin
pkgver=2.1.2
pkgrel=1
pkgdesc="Sven Package Manager for Seven OS (LFS) - PyInstaller Binary"
arch=('x86_64')
url="https://github.com/haroldmth/sven"
license=('GPL3')
depends=('git' 'gnupg' 'curl' 'tar' 'zstd')
provides=('sven')
conflicts=('sven' 'sven-git')
source=("sven-x86_64-linux::https://github.com/haroldmth/sven/releases/download/v${pkgver}/sven-linux-x86_64"
        "sven-lock-check.hook"
        "check-sven-lock.sh"
        "sven-aur-upgrade-block.hook"
        "check-sven-aur-upgrade.sh"
        "sven-delegate-remove.hook"
        "delegate-sven-remove.sh")
sha256sums=('SKIP'  # sven binary — use actual sha256 in production
            'SKIP'  # sven-lock-check.hook
            'SKIP'  # check-sven-lock.sh
            'SKIP'  # sven-aur-upgrade-block.hook
            'SKIP'  # check-sven-aur-upgrade.sh
            'SKIP'  # sven-delegate-remove.hook
            'SKIP') # delegate-sven-remove.sh

package() {
    # Install binary
    install -Dm755 "${srcdir}/sven-x86_64-linux" "${pkgdir}/usr/bin/sven"
    
    # Create required directory structure
    install -dm755 "${pkgdir}/var/lib/sven/installed"
    install -dm755 "${pkgdir}/var/lib/sven/sync"
    install -dm755 "${pkgdir}/var/lib/sven/aur_cache"
    install -dm755 "${pkgdir}/var/lib/sven/snapshots"
    install -dm755 "${pkgdir}/var/cache/sven/pkgs"
    install -dm755 "${pkgdir}/var/cache/sven/aur"
    install -dm755 "${pkgdir}/var/log/sven"
    install -dm755 "${pkgdir}/etc/sven/initscripts"
    install -dm755 "${pkgdir}/tmp/sven/aur"

    # Default config
    cat > "${srcdir}/sven.conf" << 'EOF'
[general]
install_root      = /
cache_dir         = /var/cache/sven
db_path           = /var/lib/sven
init_system       = sysvinit

[repos]
use_official      = true
use_aur           = true
aur_review        = prompt

[build]
parallel_jobs     = 4
keep_cache        = true

[download]
parallel_downloads = 5
mirror             = auto

[upgrade]
ignored_packages  =
held_packages     =
EOF
    install -Dm644 "${srcdir}/sven.conf" "${pkgdir}/etc/sven/sven.conf"

    # Install ALPM hook so pacman respects Sven's lock
    install -Dm644 "${srcdir}/sven-lock-check.hook" "${pkgdir}/usr/share/libalpm/hooks/sven-lock-check.hook"
    install -Dm755 "${srcdir}/check-sven-lock.sh" "${pkgdir}/usr/lib/sven/check-sven-lock.sh"

    # Install ALPM hook to block pacman from upgrading Sven-AUR packages
    install -Dm644 "${srcdir}/sven-aur-upgrade-block.hook" "${pkgdir}/usr/share/libalpm/hooks/sven-aur-upgrade-block.hook"
    install -Dm755 "${srcdir}/check-sven-aur-upgrade.sh" "${pkgdir}/usr/lib/sven/check-sven-aur-upgrade.sh"

    # Install ALPM hook to delegate Sven package removal to Sven
    install -Dm644 "${srcdir}/sven-delegate-remove.hook" "${pkgdir}/usr/share/libalpm/hooks/sven-delegate-remove.hook"
    install -Dm755 "${srcdir}/delegate-sven-remove.sh" "${pkgdir}/usr/lib/sven/delegate-sven-remove.sh"
}
