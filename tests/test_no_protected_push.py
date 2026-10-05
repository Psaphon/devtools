"""dtl must never push develop or main: status updates ride on the feature branch."""

import ast
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from dtl import PROTECTED_BRANCHES, _commit_merged_status, _git_push_branch, _parse_devplan

DTL = Path(__file__).parent.parent / "dtl.py"

PLAN = """\
# Development Plan: Test

## Feature: alpha

**Branch:** `feature/alpha`
**Depends on:** none
**Status:** In Progress
**Requires:** ai
"""


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, Path]:
    """A clone on feature/alpha whose origin is a local bare repo with develop."""
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "--bare", "-b", "develop", str(remote))
    work = tmp_path / "work"
    _git(tmp_path, "clone", str(remote), str(work))
    _git(work, "config", "user.email", "test@test.com")
    _git(work, "config", "user.name", "Test")
    _git(work, "checkout", "-b", "develop")
    (work / "docs").mkdir()
    (work / "docs" / "DEVPLAN.md").write_text(PLAN)
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "-u", "origin", "develop")
    _git(work, "checkout", "-b", "feature/alpha")
    return work, remote


@pytest.mark.parametrize("branch", PROTECTED_BRANCHES)
def test_push_refuses_protected_branch(tmp_path: Path, branch: str) -> None:
    with patch("dtl.subprocess.run") as run:
        assert _git_push_branch(tmp_path, branch) is False
    run.assert_not_called()


def test_push_helper_is_the_only_git_push() -> None:
    """Any other `git push` call site would bypass the protected-branch guard."""
    tree = ast.parse(DTL.read_text())
    sites = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.List)
                and len(node.elts) >= 2
                and all(isinstance(e, ast.Constant) for e in node.elts[:2])
                and [e.value for e in node.elts[:2]] == ["git", "push"]
            ):
                sites.append(fn.name)
    assert sites == ["_git_push_branch"]


def test_status_lands_on_feature_branch_not_develop(repo: tuple[Path, Path]) -> None:
    work, remote = repo
    develop_before = _git(remote, "rev-parse", "develop")
    plan = work / "docs" / "DEVPLAN.md"

    ok = _commit_merged_status(
        work, plan, "alpha", "feature/alpha", "https://github.com/o/r/pull/7"
    )

    assert ok is True
    assert _git(remote, "rev-parse", "develop") == develop_before
    remote_plan = _git(remote, "show", "feature/alpha:docs/DEVPLAN.md")
    _, features = _parse_devplan(remote_plan)
    assert features[0]["status"] == "Merged (#7)"
    assert _git(work, "status", "--porcelain") == ""


def test_status_refused_when_checkout_is_on_develop(repo: tuple[Path, Path]) -> None:
    work, _ = repo
    _git(work, "checkout", "develop")
    head_before = _git(work, "rev-parse", "HEAD")
    plan = work / "docs" / "DEVPLAN.md"

    ok = _commit_merged_status(work, plan, "alpha", "develop", "https://github.com/o/r/pull/7")

    assert ok is False
    assert _git(work, "rev-parse", "HEAD") == head_before
    assert plan.read_text() == PLAN


def test_status_refused_when_checkout_is_not_the_branch(repo: tuple[Path, Path]) -> None:
    work, _ = repo
    _git(work, "checkout", "develop")
    plan = work / "docs" / "DEVPLAN.md"

    ok = _commit_merged_status(
        work, plan, "alpha", "feature/alpha", "https://github.com/o/r/pull/7"
    )

    assert ok is False
    assert plan.read_text() == PLAN
