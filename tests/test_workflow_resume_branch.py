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
