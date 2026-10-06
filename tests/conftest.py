"""Shared fixtures: keep the suite off the real machine.

- Every test gets its own XDG_STATE_HOME / XDG_CONFIG_HOME / XDG_CACHE_HOME under tmp_path.
- A session guard fails the run if the real dtl state dir was touched.
- ``exec_dir`` hands out a scratch dir that is executable even when /tmp is
  mounted noexec, so fake CLIs really run instead of falling through to the
  real binaries.
"""

import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
FAKES_ROOT = REPO_ROOT / ".pytest-fakes"


def _real_state_dir() -> Path:
    xdg = os.environ.get("XDG_STATE_HOME", "")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / "dtl"


_REAL_STATE_DIR = _real_state_dir()


def _snapshot(root: Path) -> dict[str, tuple[int, int]]:
    if not root.exists():
        return {}
    snap = {}
    for p in sorted(root.rglob("*")):
        try:
            st = p.stat()
        except OSError:
            continue
        snap[str(p.relative_to(root))] = (st.st_mtime_ns, st.st_size)
    return snap


def _can_exec(directory: Path) -> bool:
    probe = directory / "probe.sh"
    try:
        probe.write_text("#!/bin/sh\nexit 0\n")
        probe.chmod(0o755)
        return subprocess.run([str(probe)], check=False, capture_output=True).returncode == 0
    except OSError:
        return False
    finally:
        probe.unlink(missing_ok=True)


@pytest.fixture(scope="session", autouse=True)
def _real_state_untouched() -> Iterator[None]:
    before = _snapshot(_REAL_STATE_DIR)
    yield
    after = _snapshot(_REAL_STATE_DIR)
    if before != after:
        changed = sorted(k for k in after if before.get(k) != after[k])
        removed = sorted(set(before) - set(after))
        pytest.fail(
            f"test suite modified the real state dir {_REAL_STATE_DIR}: "
            f"changed/added={changed} removed={removed}",
            pytrace=False,
        )


@pytest.fixture(autouse=True)
def _isolated_xdg(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sibling of tmp_path, not inside it: some tests assert tmp_path stays empty.
    root = tmp_path_factory.mktemp("xdg")
    state = root / "state"
    config = root / "config"
    cache = root / "cache"
    state.mkdir()
    config.mkdir()
    cache.mkdir()
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))


@pytest.fixture
def exec_dir(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """A fresh directory where scripts can be executed, even if /tmp is noexec."""
    base = Path(tmp_path_factory.getbasetemp())
    if _can_exec(base):
        d = Path(tempfile.mkdtemp(dir=base))
        cleanup = False
    else:
        FAKES_ROOT.mkdir(exist_ok=True)
        if not _can_exec(FAKES_ROOT):
            pytest.fail(f"no executable scratch dir available (tried {base}, {FAKES_ROOT})")
        d = Path(tempfile.mkdtemp(dir=FAKES_ROOT))
        cleanup = True
    yield d
    if cleanup:
        shutil.rmtree(d, ignore_errors=True)
