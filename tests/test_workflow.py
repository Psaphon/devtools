"""Tests for dtl workflow subcommands: plan parsing, branch logic, status updates."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure dtl.py is importable from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dtl import (
    _build_ai_prompt,
    _git_is_dirty,
    _parse_devplan,
    _update_feature_status,
)

# ---------------------------------------------------------------------------
# Sample DEVPLAN fixture
# ---------------------------------------------------------------------------

SAMPLE_PLAN = """\
# Development Plan: Test Project

**Status:** In Progress

## Overview

Test project overview.

## Constraints

- Single file, stdlib-only
- Must work offline

---

## Feature: alpha-feature

**Branch:** `feature/alpha-feature`
**Depends on:** none
**Status:** Done

### Goal

Alpha goal.

### Acceptance Criteria

- [ ] Alpha criterion

---

## Feature: beta-feature

**Branch:** `feature/beta-feature`
**Depends on:** alpha-feature
**Status:** Not Started

### Goal

Beta goal.

### Acceptance Criteria

- [ ] Beta criterion

### Notes

Some notes here.

---

## Feature: gamma-feature

**Branch:** `feature/gamma-feature`
**Depends on:** beta-feature
**Status:** Not Started

### Goal

Gamma goal.
"""


# ---------------------------------------------------------------------------
# _parse_devplan
# ---------------------------------------------------------------------------


class TestParseDevplan:
    def test_returns_correct_feature_count(self):
        _, features = _parse_devplan(SAMPLE_PLAN)
        assert len(features) == 3

    def test_feature_names(self):
        _, features = _parse_devplan(SAMPLE_PLAN)
        names = [f["name"] for f in features]
        assert names == ["alpha-feature", "beta-feature", "gamma-feature"]

    def test_branch_parsed_from_backtick_syntax(self):
        _, features = _parse_devplan(SAMPLE_PLAN)
        assert features[0]["branch"] == "feature/alpha-feature"
        assert features[1]["branch"] == "feature/beta-feature"

    def test_status_parsed(self):
        _, features = _parse_devplan(SAMPLE_PLAN)
        assert features[0]["status"] == "Done"
        assert features[1]["status"] == "Not Started"
        assert features[2]["status"] == "Not Started"

    def test_depends_on_parsed(self):
        _, features = _parse_devplan(SAMPLE_PLAN)
        assert features[0]["depends_on"] == "none"
        assert features[1]["depends_on"] == "alpha-feature"

    def test_constraints_block_extracted(self):
        constraints, _ = _parse_devplan(SAMPLE_PLAN)
        assert "Single file, stdlib-only" in constraints
        assert "Must work offline" in constraints

    def test_block_contains_full_section(self):
        _, features = _parse_devplan(SAMPLE_PLAN)
        beta = features[1]
        assert "## Feature: beta-feature" in beta["block"]
        assert "Beta goal." in beta["block"]
        assert "Some notes here." in beta["block"]

    def test_empty_plan_returns_no_features(self):
        constraints, features = _parse_devplan("# Development Plan\n\nNothing here.\n")
        assert features == []

    def test_no_constraints_section(self):
        minimal = (
            "## Feature: solo\n\n**Branch:** `feature/solo`\n**Status:** Not Started\n"
        )
        constraints, features = _parse_devplan(minimal)
        assert constraints == ""
        assert len(features) == 1

    def test_branch_fallback_when_no_branch_field(self):
        plan = "## Feature: my-thing\n\n**Status:** Not Started\n"
        _, features = _parse_devplan(plan)
        assert features[0]["branch"] == "feature/my-thing"

    def test_status_unknown_when_missing(self):
        plan = "## Feature: no-status\n\nNo status line here.\n"
        _, features = _parse_devplan(plan)
        assert features[0]["status"] == "Unknown"


# ---------------------------------------------------------------------------
# _update_feature_status
# ---------------------------------------------------------------------------


class TestUpdateFeatureStatus:
    def test_updates_not_started_to_in_progress(self, tmp_path):
        plan_file = tmp_path / "DEVPLAN.md"
        plan_file.write_text(SAMPLE_PLAN)
        _update_feature_status(plan_file, "beta-feature", "In Progress")
        updated = plan_file.read_text()
        assert "**Status:** In Progress" in updated
        # alpha-feature status should be unchanged
        _, features = _parse_devplan(updated)
        alpha = next(f for f in features if f["name"] == "alpha-feature")
        assert alpha["status"] == "Done"

    def test_updates_only_target_feature(self, tmp_path):
        plan_file = tmp_path / "DEVPLAN.md"
        plan_file.write_text(SAMPLE_PLAN)
        _update_feature_status(plan_file, "beta-feature", "In Progress")
        _, features = _parse_devplan(plan_file.read_text())
        gamma = next(f for f in features if f["name"] == "gamma-feature")
        assert gamma["status"] == "Not Started"

    def test_raises_on_missing_feature(self, tmp_path):
        plan_file = tmp_path / "DEVPLAN.md"
        plan_file.write_text(SAMPLE_PLAN)
        with pytest.raises(ValueError, match="nonexistent-feature"):
            _update_feature_status(plan_file, "nonexistent-feature", "In Progress")


# ---------------------------------------------------------------------------
# _build_ai_prompt
# ---------------------------------------------------------------------------


class TestBuildAiPrompt:
    def test_contains_constraints_block(self):
        _, features = _parse_devplan(SAMPLE_PLAN)
        constraints, _ = _parse_devplan(SAMPLE_PLAN)
        prompt = _build_ai_prompt(constraints, features[1])
        assert "Single file, stdlib-only" in prompt

    def test_contains_feature_block(self):
        constraints, features = _parse_devplan(SAMPLE_PLAN)
        prompt = _build_ai_prompt(constraints, features[1])
        assert "## Feature: beta-feature" in prompt
        assert "Beta goal." in prompt

    def test_no_constraints_still_includes_feature(self):
        _, features = _parse_devplan(SAMPLE_PLAN)
        prompt = _build_ai_prompt("", features[1])
        assert "## Feature: beta-feature" in prompt


# ---------------------------------------------------------------------------
# _git_is_dirty
# ---------------------------------------------------------------------------


class TestGitIsDirty:
    def test_clean_tree_returns_false(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        assert _git_is_dirty(tmp_path) is False

    def test_untracked_file_returns_true(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        (tmp_path / "new_file.txt").write_text("hello")
        assert _git_is_dirty(tmp_path) is True

    def test_staged_change_returns_true(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        f = tmp_path / "file.txt"
        f.write_text("original")
        subprocess.run(
            ["git", "add", "file.txt"], cwd=tmp_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        f.write_text("changed")
        subprocess.run(
            ["git", "add", "file.txt"], cwd=tmp_path, check=True, capture_output=True
        )
        assert _git_is_dirty(tmp_path) is True


# ---------------------------------------------------------------------------
# cmd_workflow_list (integration via argparse)
# ---------------------------------------------------------------------------


class TestCmdWorkflowList:
    def test_lists_all_features(self, tmp_path, capsys):
        from dtl import cmd_workflow_list

        plan_file = tmp_path / "DEVPLAN.md"
        plan_file.write_text(SAMPLE_PLAN)

        args = MagicMock()
        args.plan = str(plan_file)
        cmd_workflow_list(args)

        out = capsys.readouterr().out
        assert "alpha-feature" in out
        assert "beta-feature" in out
        assert "gamma-feature" in out
        assert "Done" in out
        assert "Not Started" in out

    def test_exits_on_missing_plan(self, tmp_path):
        from dtl import cmd_workflow_list

        args = MagicMock()
        args.plan = str(tmp_path / "nonexistent.md")
        with pytest.raises(SystemExit) as exc:
            cmd_workflow_list(args)
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# cmd_workflow_next (integration with mocked git/ai)
# ---------------------------------------------------------------------------


class TestCmdWorkflowNext:
    def _make_plan(self, tmp_path, content=None):
        plan_file = tmp_path / "DEVPLAN.md"
        plan_file.write_text(content or SAMPLE_PLAN)
        return plan_file

    def test_exits_on_missing_plan(self, tmp_path):
        from dtl import cmd_workflow_next

        args = MagicMock()
        args.plan = str(tmp_path / "nonexistent.md")
        args.project = str(tmp_path)
        with pytest.raises(SystemExit) as exc:
            cmd_workflow_next(args)
        assert exc.value.code == 1

    def test_exits_on_dirty_tree(self, tmp_path):
        from dtl import cmd_workflow_next

        plan_file = self._make_plan(tmp_path)
        args = MagicMock()
        args.plan = str(plan_file)
        args.project = str(tmp_path)

        with patch("dtl._git_is_dirty", return_value=True):
            with pytest.raises(SystemExit) as exc:
                cmd_workflow_next(args)
        assert exc.value.code == 1

    def test_prints_message_when_all_done(self, tmp_path, capsys):
        from dtl import cmd_workflow_next

        all_done = SAMPLE_PLAN.replace("**Status:** Not Started", "**Status:** Done")
        plan_file = self._make_plan(tmp_path, all_done)
        args = MagicMock()
        args.plan = str(plan_file)
        args.project = str(tmp_path)

        with patch("dtl._git_is_dirty", return_value=False):
            cmd_workflow_next(args)

        out = capsys.readouterr().out
        assert "done" in out.lower() or "no" in out.lower()

    def test_creates_branch_and_updates_status(self, tmp_path):
        from dtl import cmd_workflow_next

        plan_file = self._make_plan(tmp_path)
        args = MagicMock()
        args.plan = str(plan_file)
        args.project = str(tmp_path)

        with (
            patch("dtl._git_is_dirty", return_value=False),
            patch("dtl._git_create_branch") as mock_branch,
            patch("dtl.ai_run") as mock_ai,
        ):
            cmd_workflow_next(args)

        # beta-feature is first "Not Started"
        mock_branch.assert_called_once_with(
            tmp_path, "feature/beta-feature", base="develop"
        )
        mock_ai.assert_called_once()

        # Status updated in file
        _, features = _parse_devplan(plan_file.read_text())
        beta = next(f for f in features if f["name"] == "beta-feature")
        assert beta["status"] == "In Progress"

    def test_ai_prompt_contains_feature_and_constraints(self, tmp_path):
        from dtl import cmd_workflow_next

        plan_file = self._make_plan(tmp_path)
        args = MagicMock()
        args.plan = str(plan_file)
        args.project = str(tmp_path)

        captured_prompt = []

        def capture_ai_run(project_dir, prompt):
            captured_prompt.append(prompt)

        with (
            patch("dtl._git_is_dirty", return_value=False),
            patch("dtl._git_create_branch"),
            patch("dtl.ai_run", side_effect=capture_ai_run),
        ):
            cmd_workflow_next(args)

        assert captured_prompt, "ai_run was not called"
        prompt = captured_prompt[0]
        assert "Single file, stdlib-only" in prompt
        assert "## Feature: beta-feature" in prompt
        assert "Beta goal." in prompt
