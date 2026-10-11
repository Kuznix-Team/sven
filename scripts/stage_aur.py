#!/usr/bin/env python3
"""
Stage a PKGBUILD for AUR publishing (used by .github/workflows/release.yml).

    stage_aur.py <tag> <SHA256SUMS> <aur-dir>

- sets pkgver from the tag, resets pkgrel to 1
- rewrites sha256sums with real values: the release binary's sum comes from
  SHA256SUMS; local sources (hooks/scripts) are hashed from <aur-dir>
- refuses to write a PKGBUILD that still contains SKIP checksums
"""
import hashlib
import re
import sys
from pathlib import Path


def stage(tag: str, sums_file: str, aur_dir: str) -> str:
    aur = Path(aur_dir)
    pk = (aur / "PKGBUILD").read_text()

    pk = re.sub(r"(?m)^pkgver=.*$", f"pkgver={tag.lstrip('v')}", pk)
    pk = re.sub(r"(?m)^pkgrel=.*$", "pkgrel=1", pk)

    binsum = Path(sums_file).read_text().split()[0]

    src = re.search(r"source=\((.*?)\)", pk, re.S).group(1)
    names = re.findall(r'"([^"]+)"', src)
    sums = []
    for n in names:
        if "::" in n:  # name::url -> the downloaded release binary
            sums.append(binsum)
        else:          # local file shipped beside the PKGBUILD
            sums.append(hashlib.sha256((aur / n).read_bytes()).hexdigest())

    block = "sha256sums=(" + "\n            ".join(f"'{s}'" for s in sums) + ")"
    # entries may carry trailing "# comments", including after the closing paren
    pk, n = re.subn(
        r"sha256sums=\((?:\s*'[^']*'[ \t]*(?:#[^\n]*)?)*\s*\)[^\n]*",
        block, pk, count=1,
    )
    if n != 1 or "SKIP" in pk.split("package()")[0]:
        raise SystemExit("error: sha256sums were not rewritten; refusing to publish")
    if len(sums) != len(names):
        raise SystemExit("error: checksum count does not match sources")

    (aur / "PKGBUILD").write_text(pk)
    return pk


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    stage(*sys.argv[1:])
