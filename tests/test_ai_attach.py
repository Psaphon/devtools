"""Tests for dtl ai attach CI workflow requirement."""

import argparse
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from dtl import cmd_ai_attach


def _make_args(project: Path, **kwargs) -> argparse.Namespace:
    """Build a minimal argparse.Namespace for cmd_ai_attach."""
    defaults = dict(
        project=str(project),
        provider="claude",
        mode="docker",
        model=None,
        key_source="env",
        scaffold_ci=False,
        no_ci=False,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_attach_without_ci_fails(tmp_path):
    """attach on a project with no .github/workflows/*.yml should exit 1."""
    project = tmp_path / "myproject"
    project.mkdir()

    args = _make_args(project)
    with pytest.raises(SystemExit) as exc:
        cmd_ai_attach(args)
    assert exc.value.code == 1


def test_attach_with_scaffold_ci_writes_file(tmp_path, capsys):
    """--scaffold-ci should write .github/workflows/ci.yml and proceed."""
    project = tmp_path / "myproject"
    project.mkdir()

    ci_path = project / ".github" / "workflows" / "ci.yml"
    assert not ci_path.exists()

    args = _make_args(project, scaffold_ci=True)
    cmd_ai_attach(args)  # should not raise SystemExit(1)

    assert ci_path.exists(), "CI workflow should have been written by --scaffold-ci"
    content = ci_path.read_text()
    assert "ruff check" in content
    assert "pytest" in content
    assert "pull_request" in content


def test_attach_with_no_ci_skips_check(tmp_path):
    """--no-ci should bypass the CI requirement and not write a CI file."""
    project = tmp_path / "myproject"
    project.mkdir()

    ci_path = project / ".github" / "workflows" / "ci.yml"
    assert not ci_path.exists()

    args = _make_args(project, no_ci=True)
    cmd_ai_attach(args)  # should not raise SystemExit(1)

    assert not ci_path.exists(), "CI workflow should NOT be written when --no-ci is passed"
