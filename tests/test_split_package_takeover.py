# ============================================================
#  tests/test_split_package_takeover.py
# ============================================================
"""
Reported live on an LFS system with adopted monolithic packages:

    sven install pacman
    File conflict: usr/include/systemd is owned by 'systemd', ...
    File conflict: usr/lib/libblkid.so is owned by 'util-linux', ...

1. usr/include/systemd is a *directory*; shared directories are never
   conflicts.
2. libblkid.so is a real file, but util-linux-libs / systemd-libs are Arch
   split-outs of the adopted util-linux / systemd, so ownership moves.
"""
import io
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.getcwd())

from sven.db.local_db import LocalDB
from sven.db.models import Package
from sven.exceptions import FileConflictError
from sven.resolver.file_conflict import (
    check_file_conflicts, get_package_file_list, is_split_sibling,
)


class FakeDB:
    def __init__(self, owned):
        self._owned = owned  # {name: [files]}

    def all_packages(self):
        return [Package(name=n, version="1") for n in self._owned]

    def get_files(self, name):
        return self._owned[name]


def make_archive(dirs=(), files=()):
    fd, path = tempfile.mkstemp(suffix=".tar")
    os.close(fd)
    with tarfile.open(path, "w") as tar:
        for d in dirs:
            ti = tarfile.TarInfo(d)
            ti.type = tarfile.DIRTYPE
            tar.addfile(ti)
        for f in files:
            ti = tarfile.TarInfo(f)
            ti.size = 1
            tar.addfile(ti, io.BytesIO(b"x"))
    return path


class TestDirectories(unittest.TestCase):
    def test_dirs_not_in_file_list(self):
        a = make_archive(dirs=["usr/include/systemd"], files=["usr/lib/libx.so"])
        try:
            self.assertEqual(get_package_file_list(a), ["usr/lib/libx.so"])
        finally:
            os.unlink(a)

    def test_shared_directory_is_not_a_conflict(self):
        db = FakeDB({"systemd": ["usr/include/systemd", "usr/bin/systemctl"]})
        a = make_archive(dirs=["usr/include/systemd"],
                         files=["usr/include/systemd/sd-bus.h"])
        try:
            res = check_file_conflicts(
                Package(name="systemd-libs", version="262-1"), a, db)
            self.assertEqual(res, [])
        finally:
            os.unlink(a)


class TestSplitTakeover(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB({"util-linux": ["usr/lib/libblkid.so", "usr/bin/mount"]})
        self.archive = make_archive(files=["usr/lib/libblkid.so"])
        self.pkg = Package(name="util-linux-libs", version="2.42.4-1")

    def tearDown(self):
        os.unlink(self.archive)

    def test_sibling_detection(self):
        self.assertTrue(is_split_sibling("util-linux", "util-linux-libs"))
        self.assertTrue(is_split_sibling("systemd", "systemd-libs"))
        self.assertFalse(is_split_sibling("util-linux", "glib2"))
        self.assertFalse(is_split_sibling("bash", "util-linux-libs"))

    def test_still_blocked_without_opt_in(self):
        with self.assertRaises(FileConflictError):
            check_file_conflicts(self.pkg, self.archive, self.db)

    def test_protected_owner_requires_force_protected(self):
        with self.assertRaises(FileConflictError):
            check_file_conflicts(self.pkg, self.archive, self.db,
                                 allow_split_takeover=True,
                                 protected_packages=["util-linux"])

    def test_protected_owner_with_force_protected(self):
        res = check_file_conflicts(self.pkg, self.archive, self.db,
                                   allow_split_takeover=True,
                                   protected_packages=["util-linux"],
                                   force_protected=True)
        self.assertEqual(len(res), 1)
        self.assertTrue(res[0]["takeover"])
        self.assertEqual(res[0]["owner"], "util-linux")

    def test_unprotected_owner_needs_no_flag(self):
        db = FakeDB({"systemd": ["usr/lib/libsystemd.so"]})
        a = make_archive(files=["usr/lib/libsystemd.so"])
        try:
            res = check_file_conflicts(
                Package(name="systemd-libs", version="262-1"), a, db,
                allow_split_takeover=True, protected_packages=["util-linux"])
            self.assertTrue(res[0]["takeover"])
        finally:
            os.unlink(a)

    def test_real_conflict_with_unrelated_package_still_raises(self):
        db = FakeDB({"util-linux": ["usr/lib/libblkid.so"],
                     "bash": ["usr/bin/sh"]})
        a = make_archive(files=["usr/bin/sh"])
        try:
            with self.assertRaises(FileConflictError):
                check_file_conflicts(
                    Package(name="util-linux-libs", version="1"), a, db,
                    allow_split_takeover=True, force_protected=True)
        finally:
            os.unlink(a)

    def test_error_reports_total(self):
        db = FakeDB({"bash": ["usr/bin/a", "usr/bin/b", "usr/bin/c"]})
        a = make_archive(files=["usr/bin/a", "usr/bin/b", "usr/bin/c"])
        try:
            with self.assertRaises(FileConflictError) as cm:
                check_file_conflicts(Package(name="foo", version="1"), a, db)
            self.assertEqual(cm.exception.total, 3)
            self.assertIn("+2 more", str(cm.exception))
        finally:
            os.unlink(a)


class TestDisownFiles(unittest.TestCase):
    def test_disown_rewrites_owner_file_list(self):
        with tempfile.TemporaryDirectory() as d:
            db = LocalDB.__new__(LocalDB)
            db.db_path = Path(d)
            pkg = Package(name="util-linux", version="2.41-1")
            db._cache = {"util-linux": pkg}
            db._loaded = True
            entry = Path(d) / pkg.full_name
            entry.mkdir()
            (entry / "files").write_text("usr/bin/mount\nusr/lib/libblkid.so\n")
            removed = db.disown_files("util-linux", ["/usr/lib/libblkid.so"])
            self.assertEqual(removed, 1)
            self.assertEqual(db.get_files("util-linux"), ["usr/bin/mount"])


if __name__ == "__main__":
    unittest.main()
