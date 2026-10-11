"""Regression tests for scripts/stage_aur.py (AUR PKGBUILD staging in release CI)."""
import hashlib
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("stage_aur", ROOT / "scripts" / "stage_aur.py")
stage_aur = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage_aur)

LOCAL = [
    "initscripts/sven-lock-check.hook", "scripts/check-sven-lock.sh",
    "initscripts/sven-aur-upgrade-block.hook", "scripts/check-sven-aur-upgrade.sh",
    "initscripts/sven-delegate-remove.hook", "scripts/delegate-sven-remove.sh",
]


class TestStageAur(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.aur = self.tmp / "aur"
        self.aur.mkdir()
        shutil.copy(ROOT / "PKGBUILD", self.aur / "PKGBUILD")
        for f in LOCAL:
            shutil.copy(ROOT / f, self.aur / Path(f).name)
        self.binsum = hashlib.sha256(b"binary").hexdigest()
        self.sums = self.tmp / "SHA256SUMS"
        self.sums.write_text(f"{self.binsum}  sven-linux-x86_64\n")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_rewrites_version_and_checksums(self):
        pk = stage_aur.stage("v9.9.9", str(self.sums), str(self.aur))
        self.assertIn("pkgver=9.9.9", pk)
        self.assertIn("pkgrel=1", pk)
        self.assertNotIn("SKIP", pk.split("package()")[0])
        self.assertIn(f"sha256sums=('{self.binsum}'", pk)  # binary is first
        h = hashlib.sha256((self.aur / "check-sven-lock.sh").read_bytes()).hexdigest()
        self.assertIn(h, pk)

    def test_one_checksum_per_source(self):
        pk = stage_aur.stage("v1.0.0", str(self.sums), str(self.aur))
        import re
        self.assertEqual(len(re.findall(r"'[0-9a-f]{64}'", pk)), 7)

    def test_idempotent(self):
        a = stage_aur.stage("v1.0.0", str(self.sums), str(self.aur))
        b = stage_aur.stage("v1.0.0", str(self.sums), str(self.aur))
        self.assertEqual(a, b)

    def test_release_asset_name_matches_pkgbuild(self):
        # PKGBUILD must download the asset the release workflow uploads.
        self.assertIn("/sven-linux-x86_64", (ROOT / "PKGBUILD").read_text())

    def test_missing_local_source_refuses(self):
        (self.aur / "check-sven-lock.sh").unlink()
        with self.assertRaises(FileNotFoundError):
            stage_aur.stage("v1.0.0", str(self.sums), str(self.aur))


if __name__ == "__main__":
    unittest.main()
