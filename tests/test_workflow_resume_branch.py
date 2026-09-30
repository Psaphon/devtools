"""A workflow retry must resume the feature branch from the first attempt.

On hub (2026-09-30) the first finish failed its checks; the retry ran
`git checkout -b fix/...` again, which failed because the branch existed, and
the workflow gave up with the AI's commit stranded on that branch.
"""

import subprocess
from pathlib import Path

import dtl


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "user.email", "t@example.com")
    (repo / "a.txt").write_text("a\n")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def test_new_branch_is_created_off_develop(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    dtl._git_create_branch(repo, "fix/x", base="develop")
    assert _git(repo, "branch", "--show-current") == "fix/x"


def test_existing_branch_is_resumed_with_its_commits(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    dtl._git_create_branch(repo, "fix/x", base="develop")
    (repo / "b.txt").write_text("ai work\n")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-q", "-m", "first attempt")
    ai_commit = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "develop")

    dtl._git_create_branch(repo, "fix/x", base="develop")  # the retry

    assert _git(repo, "branch", "--show-current") == "fix/x"
    assert _git(repo, "rev-parse", "HEAD") == ai_commit


def test_resumed_branch_gets_the_latest_base(tmp_path: Path) -> None:
    """A branch from before a base change must be tested against the new base."""
    repo = _repo(tmp_path)
    dtl._git_create_branch(repo, "fix/x", base="develop")
    (repo / "b.txt").write_text("ai work\n")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-q", "-m", "first attempt")
    _git(repo, "checkout", "-q", "develop")
    (repo / "ci.sh").write_text("echo ci\n")
    _git(repo, "add", "ci.sh")
    _git(repo, "commit", "-q", "-m", "base gains ci.sh")

    dtl._git_create_branch(repo, "fix/x", base="develop")

    assert _git(repo, "branch", "--show-current") == "fix/x"
    assert (repo / "ci.sh").exists(), "resumed branch is missing the base's new file"
    assert (repo / "b.txt").exists(), "resume lost the first attempt's work"


def test_resume_with_conflict_aborts_cleanly(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    dtl._git_create_branch(repo, "fix/x", base="develop")
    (repo / "a.txt").write_text("branch version\n")
    _git(repo, "commit", "-qam", "branch edit")
    _git(repo, "checkout", "-q", "develop")
    (repo / "a.txt").write_text("develop version\n")
    _git(repo, "commit", "-qam", "develop edit")

    try:
        dtl._git_create_branch(repo, "fix/x", base="develop")
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError("a conflicting resume must fail, not half-merge")
    assert _git(repo, "status", "--porcelain") == "", "merge left the tree dirty"
    assert _git(repo, "branch", "--show-current") == "develop"


def test_retry_prompt_carries_the_previous_failure() -> None:
    feature = {"name": "x", "block": "## Feature: x\n"}
    plain = dtl._build_ai_prompt("", feature)
    retry = dtl._build_ai_prompt("", feature, "FAILED tests/test_a.py::test_b - boom")
    assert "FAILED tests/test_a.py::test_b - boom" in retry
    assert "do not start over" in retry.lower()
    assert "previous attempt" not in plain.lower()


def test_feature_state_has_a_failure_output_slot() -> None:
    assert dtl._FEATURE_STATE_DEFAULT["last_failure_output"] == ""


def test_giving_up_never_writes_failed_into_the_devplan() -> None:
    """The skip path runs on develop; an uncommitted edit there blocks every later run."""
    source = Path(dtl.__file__).read_text()
    assert '_update_feature_status(plan_path, f["name"], "Failed")' not in source
    assert "gave up after {max_failures} failed attempts" in source
