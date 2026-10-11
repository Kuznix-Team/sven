import atexit
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Hermetic filesystem root ─────────────────────────────────────────────────
# sven/constants.py bakes /var/lib/sven, /etc/sven, /var/cache/sven, ... in at
# import time, and LocalDB()/SyncDB() mkdir those paths in their constructors.
# Without this, tests silently write to the real system: they pass as root and
# fail as an unprivileged user (e.g. CI). constants.py natively honours
# `--root` from sys.argv at import, so point the whole session at a throwaway
# root BEFORE sven is first imported.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

SVEN_TEST_ROOT = tempfile.mkdtemp(prefix="sven-test-root-")
atexit.register(shutil.rmtree, SVEN_TEST_ROOT, ignore_errors=True)

_saved_argv = list(sys.argv)
sys.argv = sys.argv + ["--root", SVEN_TEST_ROOT]
try:
    from sven import constants as _constants
finally:
    sys.argv = _saved_argv

if not _constants.DB_BASE.startswith(SVEN_TEST_ROOT):
    # sven.constants was imported before this conftest ran, so tests would
    # touch the real system. Refuse to continue rather than do that quietly.
    raise RuntimeError(
        f"tests are not isolated: DB_BASE={_constants.DB_BASE!r}, "
        f"expected it under {SVEN_TEST_ROOT!r}"
    )

# --root also sets Config's default install_root. Tests were written against
# install_root == "/" (e.g. LibChecker only roots its paths when it isn't "/"),
# so keep that; only where Sven keeps its DB/cache/logs/config is redirected.
# Must happen before sven.config is first imported (it copies the value).
_constants.DEFAULT_ROOT = "/"
from sven.config import get_config as _get_config  # noqa: E402

if _get_config().install_root != "/":
    raise RuntimeError("tests expect Config.install_root == '/'")


class _SimpleMocker:
    def __init__(self):
        self._patchers = []
        self.MagicMock = MagicMock

    def patch(self, target, *args, **kwargs):
        patcher = patch(target, *args, **kwargs)
        mocked = patcher.start()
        self._patchers.append(patcher)
        return mocked

    def stopall(self):
        while self._patchers:
            self._patchers.pop().stop()


@pytest.fixture
def mocker():
    helper = _SimpleMocker()
    try:
        yield helper
    finally:
        helper.stopall()
