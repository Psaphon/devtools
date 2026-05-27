"""Tests for dtl pm install."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import dtl  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_args(workspace: str, dry_run: bool = False):
    import argparse

    args = argparse.Namespace(workspace=workspace, dry_run=dry_run)
    return args


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_pm_install_copies_files(tmp_path):
    """Files from pm/ land in the target workspace."""
    args = _make_args(str(tmp_path))
    dtl.cmd_pm_install(args)

    # workspace/CLAUDE.md
    assert (tmp_path / "CLAUDE.md").exists(), "CLAUDE.md not installed"

    # .claude/settings.json
    assert (tmp_path / ".claude" / "settings.json").exists()

    # .claude/PROJECTS.md
    assert (tmp_path / ".claude" / "PROJECTS.md").exists()

    # At least one file in each subdir that exists in the source
    pm_src = dtl._pm_source_dir()
    for subdir in ("rules", "commands", "scripts"):
        src_subdir = pm_src / subdir
        if not src_subdir.is_dir():
            continue
        src_files = [f for f in src_subdir.iterdir() if f.is_file()]
        if not src_files:
            continue
        dst_subdir = tmp_path / ".claude" / subdir
        dst_files = list(dst_subdir.iterdir()) if dst_subdir.exists() else []
        assert len(dst_files) == len(src_files), (
            f"Expected {len(src_files)} files in .claude/{subdir}, got {len(dst_files)}"
        )


def test_pm_install_preserves_settings_local(tmp_path):
    """Pre-existing settings.local.json is NOT overwritten."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    local_settings = claude_dir / "settings.local.json"
    sentinel = '{"preserveMe": true}'
    local_settings.write_text(sentinel)

    args = _make_args(str(tmp_path))
    dtl.cmd_pm_install(args)

    assert local_settings.read_text() == sentinel, (
        "settings.local.json was overwritten — preservation failed"
    )


def test_pm_install_preserves_handoff(tmp_path):
    """Pre-existing HANDOFF.md is NOT overwritten."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    handoff = claude_dir / "HANDOFF.md"
    sentinel = "# My handoff\n\nDo not overwrite me.\n"
    handoff.write_text(sentinel)

    args = _make_args(str(tmp_path))
    dtl.cmd_pm_install(args)

    assert handoff.read_text() == sentinel, (
        "HANDOFF.md was overwritten — preservation failed"
    )


def test_pm_install_dry_run_no_files(tmp_path):
    """--dry-run must not write any files to the workspace."""
    args = _make_args(str(tmp_path), dry_run=True)
    dtl.cmd_pm_install(args)

    # Nothing should have been created under tmp_path
    created = list(tmp_path.rglob("*"))
    assert created == [], f"dry-run wrote files: {created}"


def test_pm_install_scripts_executable(tmp_path):
    """Shell scripts in .claude/scripts/ are chmod +x after install."""
    pm_src = dtl._pm_source_dir()
    scripts_src = pm_src / "scripts"
    if not scripts_src.is_dir() or not any(scripts_src.glob("*.sh")):
        pytest.skip("No .sh files in pm/scripts — nothing to check")

    args = _make_args(str(tmp_path))
    dtl.cmd_pm_install(args)

    scripts_dst = tmp_path / ".claude" / "scripts"
    for script in scripts_dst.glob("*.sh"):
        mode = script.stat().st_mode
        assert mode & 0o111, f"{script.name} is not executable after install"
