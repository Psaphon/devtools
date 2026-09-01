"""Tests for dtl workflow subcommands: plan parsing, branch logic, status updates."""

import contextlib
import json
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure dtl.py is importable from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dtl import (
    RunOutcome,
    _build_ai_prompt,
    _check_install_freshness,
    _classify_run,
    _emit_notify_event,
    _feature_state_path,
    _git_is_dirty,
    _maybe_notify_stalled,
    _parse_devplan,
    _read_feature_state,
    _read_workflow_state,
    _resolve_provider_chain,
    _run_lint_and_tests,
    _update_feature_status,
    _workflow_state_path,
    _write_feature_state,
    _write_workflow_state,
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
        minimal = "## Feature: solo\n\n**Branch:** `feature/solo`\n**Status:** Not Started\n"
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

    def test_no_pr_suffix_warning_present(self):
        constraints, features = _parse_devplan(SAMPLE_PLAN)
        prompt = _build_ai_prompt(constraints, features[1])
        assert "(#N) PR-number suffix" in prompt
        assert "squash-merge" in prompt


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
        subprocess.run(["git", "add", "file.txt"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        f.write_text("changed")
        subprocess.run(["git", "add", "file.txt"], cwd=tmp_path, check=True, capture_output=True)
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
        mock_branch.assert_called_once_with(tmp_path, "feature/beta-feature", base="develop")
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


# ---------------------------------------------------------------------------
# cmd_workflow_run dirty-tree spin-loop regression (issue #9)
# ---------------------------------------------------------------------------


class TestCmdWorkflowRunDirtyTreeNoSpin:
    """Regression test: dirty working tree must not cause a spin loop.

    When all projects have a dirty tree, any_work_done must remain False so
    the outer while loop exits immediately.  A floor time.sleep(60) must also
    be present when work IS done, so the loop is rate-limited even if the
    any_work_done logic were somehow wrong.
    """

    def _make_project(self, tmp_path: Path) -> Path:
        """Create a minimal project directory with a DEVPLAN.md."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "DEVPLAN.md").write_text(SAMPLE_PLAN)
        return tmp_path

    def test_dirty_tree_loop_exits_without_spin(self, tmp_path):
        """Loop exits after one pass when every project has a dirty tree."""
        from dtl import cmd_workflow_run

        project_dir = self._make_project(tmp_path)

        args = MagicMock()
        args.projects = str(project_dir)
        args.schedule = None
        args.max_failures = 3

        sleep_calls: list[float] = []

        def fake_sleep(secs: float) -> None:
            sleep_calls.append(secs)

        with (
            patch("dtl._git_is_dirty", return_value=True),
            patch("dtl.time.sleep", side_effect=fake_sleep),
            patch("dtl._setup_workflow_logger") as mock_log_setup,
        ):
            mock_logger = MagicMock()
            mock_log_setup.return_value = mock_logger
            cmd_workflow_run(args)

        # The loop must have exited — if it spun it would never return.
        # any_work_done should have stayed False, so the floor sleep (60 s)
        # was never reached and the loop broke cleanly.
        floor_sleeps = [s for s in sleep_calls if s == 60]
        assert floor_sleeps == [], (
            "Floor sleep should not fire when all projects are skipped (dirty tree); "
            f"got sleep calls: {sleep_calls}"
        )

        # Verify the dirty-skip log message fired at least once
        skip_calls = [c for c in mock_logger.info.call_args_list if "dirty" in str(c).lower()]
        assert skip_calls, "Expected at least one 'dirty' skip log message"

    def test_floor_sleep_fires_when_work_is_done(self, tmp_path):
        """Floor sleep of 60 s fires after a successful work iteration."""
        from dtl import cmd_workflow_run

        project_dir = self._make_project(tmp_path)

        args = MagicMock()
        args.projects = str(project_dir)
        args.schedule = None
        args.max_failures = 3

        sleep_calls: list[float] = []

        def fake_sleep(secs: float) -> None:
            sleep_calls.append(secs)

        # Simulate: first iteration tree is clean (work done), second is all-done
        dirty_responses = iter([False])  # clean on first real check; will raise StopIteration after

        def fake_is_dirty(path):
            try:
                return next(dirty_responses)
            except StopIteration:
                return False

        # After one branch-create + AI pass, mark all features done so loop exits
        def fake_update_status(plan_path, name, status):
            # Write Done for every feature to ensure loop terminates
            text = plan_path.read_text()
            import re as _re

            text = _re.sub(r"\*\*Status:\*\* Not Started", "**Status:** Done", text)
            plan_path.write_text(text)

        with (
            patch("dtl._git_is_dirty", side_effect=fake_is_dirty),
            patch("dtl._git_create_branch"),
            patch("dtl._update_feature_status", side_effect=fake_update_status),
            patch("dtl.time.sleep", side_effect=fake_sleep),
            patch("dtl._setup_workflow_logger") as mock_log_setup,
            patch("dtl.subprocess.run") as mock_subproc,
            patch("dtl.ai_run"),
        ):
            mock_logger = MagicMock()
            mock_log_setup.return_value = mock_logger
            mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")
            cmd_workflow_run(args)

        floor_sleeps = [s for s in sleep_calls if s == 60]
        assert floor_sleeps, (
            f"Expected at least one floor sleep(60) after work iteration; "
            f"got sleep calls: {sleep_calls}"
        )


# ---------------------------------------------------------------------------
# cmd_workflow_run log path defaults and validation
# ---------------------------------------------------------------------------


class TestCmdWorkflowRunLogPath:
    """Tests for --log default, override, and in-project rejection."""

    def _make_project(self, tmp_path: Path) -> Path:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "DEVPLAN.md").write_text(SAMPLE_PLAN)
        return tmp_path

    def test_default_log_path_uses_xdg_state_home(self, tmp_path, monkeypatch):
        """Default log goes to $XDG_STATE_HOME/dtl/<project>-workflow.log."""
        from dtl import cmd_workflow_run

        project_dir = self._make_project(tmp_path / "myproject")
        state_dir = tmp_path / "state"
        monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))

        args = MagicMock()
        args.projects = str(project_dir)
        args.schedule = None
        args.max_failures = 3
        args.log = None

        captured_log_path: list[Path] = []

        def fake_setup_logger(log_path=None):
            captured_log_path.append(log_path)
            return MagicMock()

        with (
            patch("dtl._git_is_dirty", return_value=True),
            patch("dtl._setup_workflow_logger", side_effect=fake_setup_logger),
            patch("dtl.time.sleep"),
        ):
            cmd_workflow_run(args)

        assert len(captured_log_path) == 1
        lp = captured_log_path[0]
        assert lp == state_dir / "dtl" / "myproject-workflow.log"

    def test_default_log_path_fallback_without_xdg(self, tmp_path, monkeypatch):
        """Without XDG_STATE_HOME, default falls back to ~/.local/state/dtl/."""
        from dtl import cmd_workflow_run

        project_dir = self._make_project(tmp_path / "proj")
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)

        args = MagicMock()
        args.projects = str(project_dir)
        args.schedule = None
        args.max_failures = 3
        args.log = None

        captured_log_path: list[Path] = []

        def fake_setup_logger(log_path=None):
            captured_log_path.append(log_path)
            return MagicMock()

        with (
            patch("dtl._git_is_dirty", return_value=True),
            patch("dtl._setup_workflow_logger", side_effect=fake_setup_logger),
            patch("dtl.time.sleep"),
        ):
            cmd_workflow_run(args)

        assert len(captured_log_path) == 1
        lp = captured_log_path[0]
        expected = Path.home() / ".local" / "state" / "dtl" / "proj-workflow.log"
        assert lp == expected

    def test_log_override_passes_custom_path(self, tmp_path, monkeypatch):
        """--log PATH passes the resolved custom path to _setup_workflow_logger."""
        from dtl import cmd_workflow_run

        project_dir = self._make_project(tmp_path / "proj")
        custom_log = tmp_path / "custom" / "run.log"

        args = MagicMock()
        args.projects = str(project_dir)
        args.schedule = None
        args.max_failures = 3
        args.log = str(custom_log)

        captured_log_path: list[Path] = []

        def fake_setup_logger(log_path=None):
            captured_log_path.append(log_path)
            return MagicMock()

        with (
            patch("dtl._git_is_dirty", return_value=True),
            patch("dtl._setup_workflow_logger", side_effect=fake_setup_logger),
            patch("dtl.time.sleep"),
        ):
            cmd_workflow_run(args)

        assert len(captured_log_path) == 1
        assert captured_log_path[0] == custom_log.resolve()

    def test_log_inside_project_exits_with_error(self, tmp_path, capsys):
        """--log pointing inside a project directory must exit with code 1."""
        from dtl import cmd_workflow_run

        project_dir = self._make_project(tmp_path / "proj")
        in_project_log = project_dir / "workflow.log"

        args = MagicMock()
        args.projects = str(project_dir)
        args.schedule = None
        args.max_failures = 3
        args.log = str(in_project_log)

        with pytest.raises(SystemExit) as exc:
            cmd_workflow_run(args)

        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "dirty-tree skip loop" in err

    def test_default_log_outside_project_does_not_exit(self, tmp_path, monkeypatch):
        """Default XDG log path (outside all projects) should not trigger rejection."""
        from dtl import cmd_workflow_run

        project_dir = self._make_project(tmp_path / "proj")
        state_dir = tmp_path / "state"
        monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))

        args = MagicMock()
        args.projects = str(project_dir)
        args.schedule = None
        args.max_failures = 3
        args.log = None

        with (
            patch("dtl._git_is_dirty", return_value=True),
            patch("dtl._setup_workflow_logger", return_value=MagicMock()),
            patch("dtl.time.sleep"),
        ):
            # Should not raise SystemExit
            cmd_workflow_run(args)


# ---------------------------------------------------------------------------
# Workflow stall visibility: state file writes and stall notification
# ---------------------------------------------------------------------------


class TestWriteWorkflowState:
    def test_writes_json_with_required_fields(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()

        _write_workflow_state(project_dir, "dirty_tree", 2)

        state_path = _workflow_state_path(project_dir)
        assert state_path.exists()
        state = _read_workflow_state(project_dir)
        assert state["last_skip_reason"] == "dirty_tree"
        assert state["consecutive_skips"] == 2
        assert "last_check" in state
        assert "next_retry" in state

    def test_atomic_write_uses_temp_then_rename(self, tmp_path, monkeypatch):
        """No partial file is left behind; state file appears atomically."""
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        _write_workflow_state(project_dir, "dirty_tree", 1)

        state_path = _workflow_state_path(project_dir)
        # No leftover .tmp- files
        tmp_files = list(state_path.parent.glob(".tmp-*"))
        assert tmp_files == []
        assert state_path.exists()

    def test_read_returns_empty_dict_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        assert _read_workflow_state(project_dir) == {}

    def test_consecutive_skips_accumulate_across_writes(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        for i in range(1, 4):
            _write_workflow_state(project_dir, "dirty_tree", i)
            assert _read_workflow_state(project_dir)["consecutive_skips"] == i


class TestMaybeNotifyStalled:
    def test_no_notify_below_threshold(self, tmp_path):
        from dtl import WORKFLOW_STALL_THRESHOLD

        project_dir = tmp_path / "proj"
        (project_dir / ".ai").mkdir(parents=True)
        notify_script = project_dir / ".ai" / "notify.py"
        notify_script.write_text("# fake")

        calls = []
        with patch("dtl.subprocess.run", side_effect=lambda *a, **kw: calls.append(a)):
            _maybe_notify_stalled(
                project_dir, "dirty_tree", WORKFLOW_STALL_THRESHOLD - 1, MagicMock()
            )

        assert calls == []

    def test_notify_called_at_threshold(self, tmp_path):
        from dtl import WORKFLOW_STALL_THRESHOLD

        project_dir = tmp_path / "proj"
        (project_dir / ".ai").mkdir(parents=True)
        notify_script = project_dir / ".ai" / "notify.py"
        notify_script.write_text("# fake")

        calls = []
        with patch(
            "dtl.subprocess.run",
            side_effect=lambda *a, **kw: calls.append(a) or MagicMock(returncode=0),
        ):
            _maybe_notify_stalled(project_dir, "dirty_tree", WORKFLOW_STALL_THRESHOLD, MagicMock())

        assert len(calls) == 1
        assert "notify.py" in str(calls[0])

    def test_no_notify_when_script_absent(self, tmp_path):
        from dtl import WORKFLOW_STALL_THRESHOLD

        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        calls = []
        with patch("dtl.subprocess.run", side_effect=lambda *a, **kw: calls.append(a)):
            _maybe_notify_stalled(
                project_dir, "dirty_tree", WORKFLOW_STALL_THRESHOLD + 5, MagicMock()
            )

        assert calls == []


class TestWorkflowStallVisibilityIntegration:
    """Simulated dirty-tree skip x3 triggers exactly one notify call."""

    def _make_project(self, tmp_path: Path) -> Path:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "DEVPLAN.md").write_text(SAMPLE_PLAN)
        ai_dir = tmp_path / ".ai"
        ai_dir.mkdir(parents=True)
        (ai_dir / "notify.py").write_text("# fake notify")
        return tmp_path

    def _run_once(self, project_dir: Path, notify_calls: list, state_dir: Path) -> None:
        from dtl import cmd_workflow_run

        args = MagicMock()
        args.projects = str(project_dir)
        args.schedule = None
        args.max_failures = 3
        args.log = None

        def fake_subprocess_run(cmd, **kwargs):
            if any("notify.py" in str(c) for c in cmd):
                notify_calls.append(list(cmd))
            return MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("dtl._git_is_dirty", return_value=True),
            patch("dtl._setup_workflow_logger", return_value=MagicMock()),
            patch("dtl.time.sleep"),
            patch("dtl.subprocess.run", side_effect=fake_subprocess_run),
        ):
            cmd_workflow_run(args)

    def test_dirty_tree_skip_x3_triggers_one_notify_call(self, tmp_path, monkeypatch):
        state_dir = tmp_path / "state"
        monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))
        project_dir = self._make_project(tmp_path / "myproject")

        notify_calls: list = []
        for _ in range(3):
            self._run_once(project_dir, notify_calls, state_dir)

        assert len(notify_calls) == 1, (
            f"Expected exactly 1 notify call after 3 consecutive skips; got {notify_calls}"
        )

    def test_state_file_written_on_each_skip(self, tmp_path, monkeypatch):
        state_dir = tmp_path / "state"
        monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))
        project_dir = self._make_project(tmp_path / "myproject")

        notify_calls: list = []
        for i in range(1, 4):
            self._run_once(project_dir, notify_calls, state_dir)
            state = _read_workflow_state(project_dir)
            assert state["consecutive_skips"] == i
            assert state["last_skip_reason"] == "dirty_tree"


class TestCmdWorkflowStatus:
    def _make_project(self, tmp_path: Path) -> Path:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "DEVPLAN.md").write_text(SAMPLE_PLAN)
        return tmp_path

    def test_prints_no_state_when_file_absent(self, tmp_path, monkeypatch, capsys):
        from dtl import cmd_workflow_status

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = self._make_project(tmp_path / "proj")

        args = MagicMock()
        args.plan = str(project_dir / "docs" / "DEVPLAN.md")
        cmd_workflow_status(args)

        out = capsys.readouterr().out
        assert "no run state" in out.lower()

    def test_prints_state_when_file_present(self, tmp_path, monkeypatch, capsys):
        from dtl import cmd_workflow_status

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = self._make_project(tmp_path / "proj")

        _write_workflow_state(project_dir, "dirty_tree", 2)

        args = MagicMock()
        args.plan = str(project_dir / "docs" / "DEVPLAN.md")
        cmd_workflow_status(args)

        out = capsys.readouterr().out
        assert "dirty_tree" in out
        assert "2" in out
        assert "proj" in out

    def test_shows_per_feature_state(self, tmp_path, monkeypatch, capsys):
        from dtl import cmd_workflow_status

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = self._make_project(tmp_path / "proj")

        # Write a per-feature state for beta-feature
        _write_feature_state(
            project_dir,
            "beta-feature",
            {
                "last_outcome": RunOutcome.FAILED_AI,
                "last_run_iso": "2026-05-16T00:00:00+00:00",
                "attempts_completed": 2,
                "attempts_interrupted": 1,
                "partial_work_branch": None,
            },
        )

        args = MagicMock()
        args.plan = str(project_dir / "docs" / "DEVPLAN.md")
        cmd_workflow_status(args)

        out = capsys.readouterr().out
        assert "beta-feature" in out
        assert "FAILED_AI" in out
        assert "2" in out  # attempts_completed

    def test_exits_on_missing_plan(self, tmp_path, monkeypatch):
        from dtl import cmd_workflow_status

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        args = MagicMock()
        args.plan = str(tmp_path / "nonexistent" / "DEVPLAN.md")
        with pytest.raises(SystemExit) as exc:
            cmd_workflow_status(args)
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# _run_lint_and_tests: pip install step
# ---------------------------------------------------------------------------


class TestRunLintAndTestsPipInstall:
    """Unit tests for the editable install step in _run_lint_and_tests."""

    def test_pyproject_present_triggers_pip_install(self, tmp_path):
        """When pyproject.toml exists, pip install is invoked before tests."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")

        pip_calls = []

        def fake_run(cmd, **kwargs):
            if "pip" in cmd:
                pip_calls.append(list(cmd))
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("dtl.subprocess.run", side_effect=fake_run):
            _run_lint_and_tests(tmp_path)

        assert pip_calls, "Expected at least one pip install call"
        assert any("pip" in " ".join(c) for c in pip_calls)
        assert any("--break-system-packages" in c for c in pip_calls), (
            "pip command must include --break-system-packages (PEP 668 / ephemeral workstation)"
        )

    def test_no_pyproject_skips_pip_install(self, tmp_path):
        """When no pyproject.toml, pip install is never called."""
        (tmp_path / "package.json").write_text('{"name": "test"}')

        pip_calls = []

        def fake_run(cmd, **kwargs):
            if "pip" in " ".join(str(c) for c in cmd):
                pip_calls.append(list(cmd))
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("dtl.subprocess.run", side_effect=fake_run):
            _run_lint_and_tests(tmp_path)

        assert pip_calls == [], f"Expected no pip calls, got: {pip_calls}"

    def test_pip_failure_returns_failed_with_output(self, tmp_path):
        """When pip install fails (both dev and plain), gate returns failed with output."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")

        def fake_run(cmd, **kwargs):
            if "pip" in " ".join(str(c) for c in cmd):
                return MagicMock(returncode=1, stdout="", stderr="pip error: no module")
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("dtl.subprocess.run", side_effect=fake_run):
            passed, output = _run_lint_and_tests(tmp_path)

        assert not passed
        assert "pip error" in output

    def test_dev_extra_failure_falls_back_to_plain_install(self, tmp_path):
        """If .[dev] install fails, falls back to plain editable install."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")

        call_count = {"n": 0}

        def fake_run(cmd, **kwargs):
            if "pip" in " ".join(str(c) for c in cmd):
                call_count["n"] += 1
                # First pip call (.[dev]) fails, second (plain) succeeds
                if call_count["n"] == 1:
                    return MagicMock(returncode=1, stdout="", stderr="no extra 'dev'")
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("dtl.subprocess.run", side_effect=fake_run):
            passed, output = _run_lint_and_tests(tmp_path)

        assert call_count["n"] == 2, "Expected fallback to second pip install"
        assert passed


# ---------------------------------------------------------------------------
# cmd_workflow_run --schedule subprocess delegation
# ---------------------------------------------------------------------------


class TestCmdWorkflowRunScheduleSubprocess:
    """When --schedule is set, cmd_workflow_run sleeps then delegates to a fresh subprocess."""

    def test_schedule_delegates_to_subprocess(self, tmp_path, monkeypatch):
        from dtl import cmd_workflow_run

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()

        args = MagicMock()
        args.projects = str(project_dir)
        args.schedule = "02:00"
        args.max_failures = 3
        args.max_wall_clock = 1800
        args.max_ai_retries = 3
        args.log = None

        fake_result = MagicMock()
        fake_result.returncode = 42

        subprocess_calls: list[list[str]] = []

        def fake_subprocess_run(cmd, **kwargs):
            subprocess_calls.append(list(cmd))
            return fake_result

        with (
            patch("dtl.time.sleep"),
            patch("dtl.subprocess.run", side_effect=fake_subprocess_run),
            patch("dtl._setup_workflow_logger", return_value=MagicMock()),
            patch("dtl._preflight_auto_merge", return_value=None),
            # The staleness guard sys.exit(1)s in schedule_mode when the running
            # script differs from ~/Projects/devtools/dtl.py. On a dev host that
            # path exists and never matches pytest, so without this patch the test
            # passes only in CI (where the path is absent). Bypass it to test
            # subprocess delegation in isolation.
            patch("dtl._check_install_freshness"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                cmd_workflow_run(args)

        assert len(subprocess_calls) == 1, (
            f"Expected exactly one subprocess.run call; got {subprocess_calls}"
        )
        child_argv = subprocess_calls[0]
        assert child_argv[0] == sys.executable
        assert child_argv[1] == sys.argv[0]
        assert "workflow" in child_argv
        assert "run" in child_argv
        assert "--projects" in child_argv
        assert "--schedule" not in child_argv, (
            "--schedule must NOT be forwarded to the child process"
        )
        assert exc_info.value.code == 42, (
            f"Parent must exit with child's returncode; got {exc_info.value.code}"
        )


# ---------------------------------------------------------------------------
# _preflight_auto_merge: scheduled-run rejection and warning-banner paths
# ---------------------------------------------------------------------------


class TestPreflightAutoMerge:
    """Preflight check: --schedule exits non-zero; interactive prints warning."""

    def _make_project(self, tmp_path: Path) -> Path:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "DEVPLAN.md").write_text(SAMPLE_PLAN)
        return tmp_path

    def test_schedule_exits_nonzero_when_auto_merge_disabled(self, tmp_path, monkeypatch):
        """With --schedule and allow_auto_merge=False, cmd_workflow_run exits non-zero
        and time.sleep is never called."""
        from dtl import cmd_workflow_run

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = self._make_project(tmp_path / "myproject")

        args = MagicMock()
        args.projects = str(project_dir)
        args.schedule = "02:00"
        args.max_failures = 3
        args.max_wall_clock = 1800
        args.max_ai_retries = 3
        args.log = None

        sleep_calls: list = []

        with (
            patch("dtl._preflight_auto_merge", return_value=False),
            patch("dtl.time.sleep", side_effect=lambda s: sleep_calls.append(s)),
            patch("dtl._setup_workflow_logger", return_value=MagicMock()),
        ):
            with pytest.raises(SystemExit) as exc_info:
                cmd_workflow_run(args)

        assert exc_info.value.code != 0, (
            "Expected non-zero exit when allow_auto_merge=False and --schedule is set"
        )
        assert sleep_calls == [], (
            f"time.sleep must not be called before the preflight exits; got {sleep_calls}"
        )

    def test_no_schedule_logs_warning_and_continues(self, tmp_path, monkeypatch):
        """Without --schedule and allow_auto_merge=False, cmd_workflow_run logs a
        WARNING banner naming the repo and continues execution (does not exit)."""
        from dtl import cmd_workflow_run

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = self._make_project(tmp_path / "myproject")

        args = MagicMock()
        args.projects = str(project_dir)
        args.schedule = None
        args.max_failures = 3
        args.max_wall_clock = 1800
        args.max_ai_retries = 3
        args.log = None

        mock_logger = MagicMock()

        with (
            patch("dtl._preflight_auto_merge", return_value=False),
            patch("dtl._git_is_dirty", return_value=True),
            patch("dtl.time.sleep"),
            patch("dtl._setup_workflow_logger", return_value=mock_logger),
        ):
            # Must NOT raise SystemExit
            cmd_workflow_run(args)

        warning_calls = [
            c
            for c in mock_logger.warning.call_args_list
            if "allow_auto_merge" in str(c) or "manual merge" in str(c).lower()
        ]
        assert warning_calls, (
            "Expected a warning log about allow_auto_merge / manual merge; "
            f"warning calls: {mock_logger.warning.call_args_list}"
        )


# ---------------------------------------------------------------------------
# AI failure snapshot
# ---------------------------------------------------------------------------


class TestAiFailureSnapshot:
    """Tests for _write_failure_snapshot and cmd_workflow_run snapshot integration."""

    def _make_project(self, tmp_path: Path) -> Path:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "DEVPLAN.md").write_text(SAMPLE_PLAN)
        return tmp_path

    def test_ai_exit1_produces_snapshot_with_required_sections(self, tmp_path, monkeypatch):
        """Simulated AI exit-1 writes a snapshot file containing all required sections."""
        from dtl import cmd_workflow_run

        state_dir = tmp_path / "state"
        monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))

        # Use a plan with a single Not Started feature so the loop terminates
        # cleanly after one failure (max_failures=1) and only one snapshot is written.
        single_feature_plan = """\
# Development Plan: Single Feature

## Constraints

- Single file, stdlib-only

---

## Feature: beta-feature

**Branch:** `feature/beta-feature`
**Depends on:** none
**Status:** Not Started

### Goal

Beta goal.

### Acceptance Criteria

- [ ] Beta criterion
"""
        project_dir = tmp_path / "myproject"
        docs_dir = project_dir / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "DEVPLAN.md").write_text(single_feature_plan)

        args = MagicMock()
        args.projects = str(project_dir)
        args.schedule = None
        args.max_failures = 1
        args.max_wall_clock = 1800
        args.max_ai_retries = 3
        args.log = None

        mock_logger = MagicMock()

        def fake_subprocess_run(cmd, **kwargs):
            # AI subprocess call returns exit code 1 with recognisable output
            if sys.executable in str(cmd) or (isinstance(cmd, list) and "claude" in cmd[0]):
                return MagicMock(
                    returncode=1,
                    stdout="stdout line 1\n",
                    stderr="stderr line 1\n",
                )
            # git calls succeed and return useful data
            if isinstance(cmd, list):
                if "status" in cmd:
                    return MagicMock(returncode=0, stdout="M  foo.py\n", stderr="")
                if "diff" in cmd and "--stat" in cmd:
                    return MagicMock(returncode=0, stdout="foo.py | 1 +\n", stderr="")
                if "diff" in cmd:
                    return MagicMock(returncode=0, stdout="+added line\n", stderr="")
                if "ls-files" in cmd:
                    return MagicMock(returncode=0, stdout="untracked.py\n", stderr="")
                if "checkout" in cmd or "pull" in cmd:
                    return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("dtl._git_is_dirty", return_value=False),
            patch("dtl._git_create_branch"),
            patch("dtl._setup_workflow_logger", return_value=mock_logger),
            patch("dtl.subprocess.run", side_effect=fake_subprocess_run),
            patch("dtl.time.sleep"),
        ):
            cmd_workflow_run(args)

        snapshot_dir = state_dir / "dtl"
        snapshots = list(snapshot_dir.glob("myproject-*-failure-*.md"))
        assert len(snapshots) == 1, f"Expected 1 snapshot file; found {snapshots}"

        content = snapshots[0].read_text()
        assert "**Project:**" in content
        assert "**Feature:**" in content
        assert "**Branch:**" in content
        assert "**AI exit code:**" in content
        assert "**Wall-clock duration:**" in content
        assert "## Last 200 Lines of AI Output" in content
        assert "## Git Status" in content
        assert "## Diff Stat" in content
        assert "## Full Diff" in content
        assert "## Untracked Files" in content
        # Snapshot path logged
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("failure snapshot written" in c for c in info_calls), (
            f"Expected 'failure snapshot written' log; got {info_calls}"
        )

    def test_snapshot_write_failure_does_not_raise(self, tmp_path, monkeypatch):
        """If snapshot directory is unwritable, cmd_workflow_run does not raise."""
        from dtl import cmd_workflow_run

        state_dir = tmp_path / "state"
        monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))
        project_dir = self._make_project(tmp_path / "myproject")

        args = MagicMock()
        args.projects = str(project_dir)
        args.schedule = None
        args.max_failures = 3
        args.max_wall_clock = 1800
        args.max_ai_retries = 3
        args.log = None

        def fake_subprocess_run(cmd, **kwargs):
            if sys.executable in str(cmd) or (isinstance(cmd, list) and "claude" in cmd[0]):
                return MagicMock(returncode=1, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        def exploding_write_snapshot(*args, **kwargs):
            raise OSError("disk full")

        with (
            patch("dtl._git_is_dirty", return_value=False),
            patch("dtl._git_create_branch"),
            patch("dtl._setup_workflow_logger", return_value=MagicMock()),
            patch("dtl.subprocess.run", side_effect=fake_subprocess_run),
            patch("dtl._write_failure_snapshot", side_effect=exploding_write_snapshot),
            patch("dtl.time.sleep"),
        ):
            # Must not raise
            cmd_workflow_run(args)


# ---------------------------------------------------------------------------
# Notify hook tests
# ---------------------------------------------------------------------------


class TestEmitNotifyEventAiFailure:
    """_emit_notify_event sends an ai-failure event with the correct JSON shape."""

    def test_ai_failure_event_shape(self, tmp_path):
        """ai-failure POST body contains event, event_id, timestamp, and payload fields."""
        import json
        import logging

        posted_bodies: list[dict] = []

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def fake_urlopen(req, timeout=None):
            posted_bodies.append(json.loads(req.data.decode()))
            return FakeResponse()

        cfg = {
            "url": "https://ntfy.example.ts.net/dtl",
            "events": ["ai-failure", "feature-merged", "needs-attention", "idle"],
            "retry_seconds": [0],
        }
        log = logging.getLogger("test.ai_failure")

        with patch("dtl.urllib.request.urlopen", side_effect=fake_urlopen):
            _emit_notify_event(
                cfg,
                "ai-failure",
                {
                    "project": "myproject",
                    "feature": "beta-feature",
                    "exit_code": 1,
                    "failure_snapshot_path": "/tmp/snap.md",
                },
                log,
            )

        assert len(posted_bodies) == 1, "Expected exactly one POST"
        body = posted_bodies[0]
        assert body["event"] == "ai-failure"
        assert "event_id" in body and len(body["event_id"]) == 16
        assert "timestamp" in body
        assert body["project"] == "myproject"
        assert body["feature"] == "beta-feature"
        assert body["exit_code"] == 1
        assert body["failure_snapshot_path"] == "/tmp/snap.md"
        assert "actions" in body


class TestEmitNotifyEventFeatureMerged:
    """cmd_workflow_run emits feature-merged event when a PR is detected as merged."""

    def _make_project(self, tmp_path: Path) -> Path:
        plan = """\
# Development Plan: Test

## Feature: beta-feature

**Branch:** `feature/beta-feature`
**Depends on:** none
**Status:** Not Started

### Goal

Beta goal.

### Acceptance Criteria

- [ ] Beta criterion
"""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "DEVPLAN.md").write_text(plan)
        return tmp_path

    def test_feature_merged_event_emitted_on_pr_merge(self, tmp_path, monkeypatch):
        """When the poll loop detects MERGED, a feature-merged event is emitted."""
        from dtl import cmd_workflow_run

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = self._make_project(tmp_path / "myproject")

        args = MagicMock()
        args.projects = str(project_dir)
        args.schedule = None
        args.max_failures = 3
        args.max_wall_clock = 1800
        args.max_ai_retries = 3
        args.log = None

        emitted_events: list[dict] = []

        def fake_emit(cfg, event_type, payload, log):
            emitted_events.append({"event": event_type, **payload})

        def fake_update_status(plan_path_arg, name, status):
            # Use the real implementation so the plan file is updated, terminating the loop
            _update_feature_status(plan_path_arg, name, status)

        with (
            patch("dtl._git_is_dirty", return_value=False),
            patch("dtl._git_create_branch"),
            patch("dtl._setup_workflow_logger", return_value=MagicMock()),
            patch(
                "dtl._load_notify_config",
                return_value={"url": "https://example.com", "events": []},
            ),
            patch("dtl._emit_notify_event", side_effect=fake_emit),
            patch(
                "dtl.subprocess.run",
                return_value=MagicMock(returncode=0, stdout="", stderr=""),
            ),
            patch("dtl.ai_run"),
            patch("dtl._run_lint_and_tests", return_value=(True, "")),
            patch("dtl._git_push_branch", return_value=True),
            patch("dtl._gh_create_pr", return_value="https://github.com/org/repo/pull/7"),
            patch("dtl._gh_enable_auto_merge", return_value=True),
            patch("dtl._gh_pr_state", return_value="MERGED"),
            patch("dtl._update_feature_status", side_effect=fake_update_status),
            patch("dtl.time.sleep"),
        ):
            cmd_workflow_run(args)

        merged_events = [e for e in emitted_events if e["event"] == "feature-merged"]
        assert merged_events, f"Expected feature-merged event; got {emitted_events}"
        ev = merged_events[0]
        assert ev["project"] == "myproject"
        assert ev["feature"] == "beta-feature"
        assert ev["pr_number"] == 7


class TestNotifyDeliveryFailureNonFatal:
    """Delivery failures from _emit_notify_event never raise and never block the workflow."""

    def test_urlopen_exception_is_swallowed(self):
        """When urllib raises on every attempt, _emit_notify_event returns without raising."""
        import logging

        log = logging.getLogger("test.delivery_failure")
        cfg = {
            "url": "https://ntfy.example.ts.net/dtl",
            "events": [],
            "retry_seconds": [0, 0],
        }

        def exploding_urlopen(req, timeout=None):
            raise OSError("connection refused")

        with patch("dtl.urllib.request.urlopen", side_effect=exploding_urlopen):
            # Must not raise
            _emit_notify_event(
                cfg,
                "idle",
                {"timestamp": "2026-01-01T00:00:00+00:00"},
                log,
            )

    def test_workflow_run_continues_when_urlopen_fails(self, tmp_path, monkeypatch):
        """cmd_workflow_run exits cleanly when the notify endpoint is unreachable."""
        from dtl import cmd_workflow_run

        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        docs_dir = project_dir / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "DEVPLAN.md").write_text(
            "## Feature: solo\n\n**Branch:** `feature/solo`\n"
            "**Depends on:** none\n**Status:** Not Started\n\n### Goal\n\nSolo.\n"
        )

        args = MagicMock()
        args.projects = str(project_dir)
        args.schedule = None
        args.max_failures = 3
        args.max_wall_clock = 1800
        args.max_ai_retries = 3
        args.log = None

        def exploding_urlopen(req, timeout=None):
            raise OSError("connection refused")

        # All projects skipped (dirty tree) → idle event fired → urlopen fails.
        # Workflow must still exit cleanly.
        with (
            patch("dtl._git_is_dirty", return_value=True),
            patch("dtl._setup_workflow_logger", return_value=MagicMock()),
            patch(
                "dtl._load_notify_config",
                return_value={
                    "url": "https://ntfy.example.ts.net/dtl",
                    "events": ["idle"],
                    "retry_seconds": [0],
                },
            ),
            patch("dtl.urllib.request.urlopen", side_effect=exploding_urlopen),
            patch("dtl.time.sleep"),
        ):
            # Must not raise even though every urlopen call fails
            cmd_workflow_run(args)


# ---------------------------------------------------------------------------
# Run classification (interruption-taxonomy)
# ---------------------------------------------------------------------------


class TestRunClassification:
    """_classify_run: sentinel > tail-pattern > exit-code, in that order."""

    # --- Sentinel detection (most authoritative) ---

    def test_sentinel_completed(self):
        out = ["doing work...\n", "all done.\n", "<<<DTL:OUTCOME=COMPLETED>>>\n"]
        assert _classify_run(0, out) == RunOutcome.COMPLETED

    def test_sentinel_quota(self):
        out = ["<<<DTL:OUTCOME=INTERRUPTED_QUOTA>>>\n"]
        assert _classify_run(1, out) == RunOutcome.INTERRUPTED_QUOTA

    def test_sentinel_failed_ai(self):
        out = [
            "I cannot proceed.\n",
            "<<<DTL:OUTCOME=FAILED_AI>>>\n",
            "missing context\n",
        ]
        assert _classify_run(0, out) == RunOutcome.FAILED_AI

    def test_sentinel_unknown_falls_through_to_exit_code(self):
        out = ["<<<DTL:OUTCOME=BOGUS_VALUE>>>\n"]
        assert _classify_run(0, out) == RunOutcome.COMPLETED
        assert _classify_run(1, out) == RunOutcome.FAILED_AI

    def test_sentinel_overrides_tail_patterns(self):
        # Tail contains a quota pattern; sentinel says COMPLETED. Sentinel wins.
        out = (
            ["work...\n"] * 30
            + ["claude usage limit reached\n"]
            + ["<<<DTL:OUTCOME=COMPLETED>>>\n"]
        )
        assert _classify_run(0, out) == RunOutcome.COMPLETED

    # --- Tail-only fallback (last 50 lines) ---

    def test_tail_pattern_quota(self):
        out = ["normal work\n"] * 10 + ["claude usage limit reached\n"]
        assert _classify_run(1, out) == RunOutcome.INTERRUPTED_QUOTA

    def test_tail_pattern_auth(self):
        out = ["normal work\n"] * 10 + ["please run claude login\n"]
        assert _classify_run(1, out) == RunOutcome.INTERRUPTED_AUTH

    def test_tail_pattern_network(self):
        out = ["normal work\n"] * 10 + ["connection timed out\n"]
        assert _classify_run(1, out) == RunOutcome.INTERRUPTED_NETWORK

    def test_pattern_outside_tail_does_not_match(self):
        # Pattern in line 1 of 100; tail (last 50) is clean. Should fall to exit code.
        out = ["claude usage limit reached\n"] + ["normal work\n"] * 99
        assert _classify_run(0, out) == RunOutcome.COMPLETED

    # --- Exit-code fallback ---

    def test_exit_code_zero_completed(self):
        assert _classify_run(0, ["normal work\n"]) == RunOutcome.COMPLETED

    def test_exit_code_124_wall_clock(self):
        assert _classify_run(124, ["normal work\n"]) == RunOutcome.INTERRUPTED_WALL_CLOCK

    def test_exit_code_125_retry_cap_is_failed_ai(self):
        # 125 was the retry-cap kill — AI was looping on tests, treat as failure.
        assert _classify_run(125, ["normal work\n"]) == RunOutcome.FAILED_AI

    def test_exit_code_nonzero_failed_ai(self):
        assert _classify_run(1, ["normal work\n"]) == RunOutcome.FAILED_AI

    # --- Regression: 2026-05-14 stranded-research-worker ---

    def test_regression_completed_with_auth_string_in_body(self):
        """The bug: AI builds a Worker that contains 'authentication failed' as
        a user-facing error string. The OLD _detect_auth_failure substring-matched
        the AI's own narration of writing that code and aborted the workflow,
        stranding 1004 lines of completed, tested work.

        With sentinel + tail-only: the AI prints COMPLETED at the end, the
        narration of 'authentication failed' is somewhere in the middle of the
        output, and classification correctly returns COMPLETED.
        """
        out = (
            ["narrating: I'm writing the Cloudflare Worker now.\n"]
            + [
                "narrating: adding error handling that returns "
                "'Claude API authentication failed.'\n"
            ]
            + ["narrating: more code...\n"] * 60  # pushes auth string out of the tail
            + ["all tests pass.\n", "committed.\n", "<<<DTL:OUTCOME=COMPLETED>>>\n"]
        )
        assert _classify_run(0, out) == RunOutcome.COMPLETED

    def test_regression_no_sentinel_with_auth_in_tail_classifies_auth(self):
        """Inverse case: AI didn't print the sentinel AND the actual auth failure
        message is in the tail. Should classify as INTERRUPTED_AUTH (a real auth
        problem the human needs to address)."""
        out = ["normal work\n"] * 10 + ["please run claude login\n"]
        assert _classify_run(1, out) == RunOutcome.INTERRUPTED_AUTH

    # --- Prompt instruction ---

    def test_build_ai_prompt_includes_sentinel_instruction(self):
        feature = {
            "name": "test-feature",
            "branch": "feature/test-feature",
            "depends_on": "none",
            "status": "Not Started",
            "block": "## Feature: test-feature\n\nDo a thing.",
        }
        prompt = _build_ai_prompt("Some constraints.", feature)
        assert "<<<DTL:OUTCOME=COMPLETED>>>" in prompt
        assert "<<<DTL:OUTCOME=FAILED_AI>>>" in prompt


# ---------------------------------------------------------------------------
# Per-feature state: _read_feature_state / _write_feature_state
# ---------------------------------------------------------------------------


class TestFeatureState:
    """Tests for per-feature persistent state helpers."""

    def test_read_returns_defaults_when_absent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        state = _read_feature_state(project_dir, "my-feature")
        assert state["last_outcome"] == ""
        assert state["last_run_iso"] == ""
        assert state["attempts_completed"] == 0
        assert state["attempts_interrupted"] == 0
        assert state["partial_work_branch"] is None

    def test_write_then_read_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        written = {
            "last_outcome": RunOutcome.FAILED_AI,
            "last_run_iso": "2026-05-16T12:00:00+00:00",
            "attempts_completed": 2,
            "attempts_interrupted": 1,
            "partial_work_branch": None,
        }
        _write_feature_state(project_dir, "my-feature", written)
        read_back = _read_feature_state(project_dir, "my-feature")
        assert read_back["last_outcome"] == RunOutcome.FAILED_AI
        assert read_back["attempts_completed"] == 2
        assert read_back["attempts_interrupted"] == 1

    def test_state_path_is_under_project_subdir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()

        p = _feature_state_path(project_dir, "some-feature")
        assert p.parent.name == "myproject"
        assert p.name == "some-feature.json"

    def test_write_is_atomic_no_tmp_files(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        state = {
            "last_outcome": RunOutcome.COMPLETED,
            "last_run_iso": "2026-05-16T00:00:00+00:00",
            "attempts_completed": 0,
            "attempts_interrupted": 0,
            "partial_work_branch": None,
        }
        _write_feature_state(project_dir, "feat", state)

        p = _feature_state_path(project_dir, "feat")
        assert p.exists()
        tmp_files = list(p.parent.glob("*.tmp"))
        assert tmp_files == [], f"Leftover tmp files: {tmp_files}"

    def test_write_sets_mode_600(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        _write_feature_state(
            project_dir,
            "feat",
            {
                "last_outcome": "",
                "last_run_iso": "",
                "attempts_completed": 0,
                "attempts_interrupted": 0,
                "partial_work_branch": None,
            },
        )
        p = _feature_state_path(project_dir, "feat")
        mode = p.stat().st_mode & 0o777
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"

    def test_state_survives_simulated_process_restart(self, tmp_path, monkeypatch):
        """State written before a restart is readable after — simulated by a
        fresh call to _read_feature_state with only the XDG env set."""
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        # "Before restart": write state
        _write_feature_state(
            project_dir,
            "restart-feature",
            {
                "last_outcome": RunOutcome.INTERRUPTED_NETWORK,
                "last_run_iso": "2026-05-16T08:00:00+00:00",
                "attempts_completed": 1,
                "attempts_interrupted": 3,
                "partial_work_branch": "feature/restart-feature",
            },
        )

        # "After restart": read state (same XDG, no in-memory dict)
        recovered = _read_feature_state(project_dir, "restart-feature")
        assert recovered["last_outcome"] == RunOutcome.INTERRUPTED_NETWORK
        assert recovered["attempts_completed"] == 1
        assert recovered["attempts_interrupted"] == 3
        assert recovered["partial_work_branch"] == "feature/restart-feature"

    def test_interrupted_quota_does_not_increment_attempts_completed(self, tmp_path, monkeypatch):
        """INTERRUPTED_QUOTA must only increment attempts_interrupted, not attempts_completed."""
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        initial = _read_feature_state(project_dir, "quota-feature")
        assert initial["attempts_completed"] == 0
        assert initial["attempts_interrupted"] == 0

        # Simulate what _handle_interruption does for INTERRUPTED_QUOTA
        fstate = _read_feature_state(project_dir, "quota-feature")
        fstate["last_outcome"] = RunOutcome.INTERRUPTED_QUOTA
        fstate["attempts_interrupted"] = fstate["attempts_interrupted"] + 1
        # attempts_completed deliberately NOT incremented
        _write_feature_state(project_dir, "quota-feature", fstate)

        after = _read_feature_state(project_dir, "quota-feature")
        assert after["attempts_completed"] == 0, "INTERRUPTED_QUOTA must not burn the retry budget"
        assert after["attempts_interrupted"] == 1

    def test_failed_ai_increments_attempts_completed(self, tmp_path, monkeypatch):
        """FAILED_AI increments attempts_completed, allowing eventual Failed marking."""
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        for i in range(1, 4):
            fstate = _read_feature_state(project_dir, "failing-feature")
            fstate["last_outcome"] = RunOutcome.FAILED_AI
            fstate["attempts_completed"] = fstate["attempts_completed"] + 1
            _write_feature_state(project_dir, "failing-feature", fstate)
            assert _read_feature_state(project_dir, "failing-feature")["attempts_completed"] == i

    def test_partial_work_branch_set_on_wall_clock_interruption(self, tmp_path, monkeypatch):
        """partial_work_branch is populated on INTERRUPTED_WALL_CLOCK."""
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        fstate = _read_feature_state(project_dir, "slow-feature")
        fstate["last_outcome"] = RunOutcome.INTERRUPTED_WALL_CLOCK
        fstate["partial_work_branch"] = "feature/slow-feature"
        fstate["attempts_interrupted"] = fstate["attempts_interrupted"] + 1
        _write_feature_state(project_dir, "slow-feature", fstate)

        after = _read_feature_state(project_dir, "slow-feature")
        assert after["partial_work_branch"] == "feature/slow-feature"
        assert after["attempts_completed"] == 0


# ---------------------------------------------------------------------------
# Provider chain rotation
# ---------------------------------------------------------------------------


class TestProviderChain:
    """Tests for provider chain rotation on INTERRUPTED_QUOTA."""

    _SINGLE_FEATURE_PLAN = """\
# Development Plan: Chain Test

## Constraints

- Single file, stdlib-only

---

## Feature: alpha-feature

**Branch:** `feature/alpha-feature`
**Depends on:** none
**Status:** Not Started

### Goal

Test feature.

### Acceptance Criteria

- [ ] Done
"""

    def _make_project(
        self,
        tmp_path: Path,
        provider_chain: list | None = None,
        provider: str = "claude",
    ) -> Path:
        """Create a minimal project with optional .ai/config.json and a DEVPLAN.md."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "DEVPLAN.md").write_text(self._SINGLE_FEATURE_PLAN)
        ai_dir = tmp_path / ".ai"
        ai_dir.mkdir()
        config: dict = {
            "project_name": "chain-test",
            "provider": provider,
            "mode": "docker",
            "model": None,
            "key_source": "env",
            "notify": {
                "provider": None,
                "telegram_token": None,
                "telegram_chat_id": None,
            },
        }
        if provider_chain is not None:
            config["provider_chain"] = provider_chain
        (ai_dir / "config.json").write_text(json.dumps(config))
        return tmp_path

    # ------------------------------------------------------------------
    # Unit tests for _resolve_provider_chain
    # ------------------------------------------------------------------

    def test_resolve_chain_no_config_returns_default(self, tmp_path):
        """No .ai/config.json → returns ['claude']."""
        assert _resolve_provider_chain(tmp_path) == ["claude"]

    def test_resolve_chain_single_provider_backward_compat(self, tmp_path):
        """Config without provider_chain falls back to [config['provider']]."""
        self._make_project(tmp_path, provider="ollama")
        # provider_chain key is absent from this config
        chain = _resolve_provider_chain(tmp_path)
        assert chain == ["ollama"]

    def test_resolve_chain_explicit_chain(self, tmp_path):
        """provider_chain list is returned directly."""
        self._make_project(tmp_path, provider_chain=["claude", "ollama"])
        assert _resolve_provider_chain(tmp_path) == ["claude", "ollama"]

    def test_resolve_chain_empty_list_falls_back_to_provider(self, tmp_path):
        """An empty provider_chain list falls back to config['provider']."""
        self._make_project(tmp_path, provider_chain=[], provider="openclaw")
        assert _resolve_provider_chain(tmp_path) == ["openclaw"]

    # ------------------------------------------------------------------
    # Integration tests for cmd_workflow_run chain rotation
    # ------------------------------------------------------------------

    def _make_args(self, project_dir: Path, quota_reset_sleep: int = 3600) -> MagicMock:
        args = MagicMock()
        args.projects = str(project_dir)
        args.schedule = None
        args.max_failures = 3
        args.max_wall_clock = 1800
        args.max_ai_retries = 3
        args.quota_reset_sleep = quota_reset_sleep
        args.log = None
        return args

    def _fake_handle_interruption(self, project_dir, plan_path, feature, branch, outcome, *a, **kw):
        """Revert plan 'In Progress' → 'Not Started' as the real function does via git."""
        text = plan_path.read_text()
        text = re.sub(r"\*\*Status:\*\* In Progress", "**Status:** Not Started", text)
        plan_path.write_text(text)

    def test_chain_rotates_to_next_provider_on_interrupted_quota(self, tmp_path, monkeypatch):
        """On INTERRUPTED_QUOTA the next subprocess call uses the next chain provider."""
        from dtl import cmd_workflow_run

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = self._make_project(tmp_path / "proj", provider_chain=["claude", "ollama"])
        args = self._make_args(project_dir)

        call_providers: list[str | None] = []
        ai_call_count = [0]

        def fake_subprocess_run(cmd, **kwargs):
            if isinstance(cmd, list) and "--feature-name" in cmd:
                # AI subprocess: extract --provider value
                try:
                    idx = cmd.index("--provider")
                    call_providers.append(cmd[idx + 1])
                except ValueError:
                    call_providers.append(None)
                ai_call_count[0] += 1
                if ai_call_count[0] == 1:
                    # First call: simulate quota exhaustion
                    return MagicMock(
                        returncode=1,
                        stdout="<<<DTL:OUTCOME=INTERRUPTED_QUOTA>>>\n",
                        stderr="",
                    )
                # Second call: stop the loop
                raise SystemExit(0)
            return MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("dtl._git_is_dirty", return_value=False),
            patch("dtl._git_create_branch"),
            patch(
                "dtl._handle_interruption",
                side_effect=lambda *a, **kw: self._fake_handle_interruption(*a, **kw),
            ),
            patch("dtl.subprocess.run", side_effect=fake_subprocess_run),
            patch("dtl.time.sleep"),
            patch("dtl._setup_workflow_logger", return_value=MagicMock()),
            patch("dtl._preflight_auto_merge", return_value=None),
        ):
            with pytest.raises(SystemExit):
                cmd_workflow_run(args)

        assert len(call_providers) == 2, f"Expected 2 AI calls; got {call_providers}"
        assert call_providers[0] == "claude"
        assert call_providers[1] == "ollama"

    def test_chain_exhaustion_sleeps_quota_reset_sleep(self, tmp_path, monkeypatch):
        """When chain is exhausted, sleep(quota_reset_sleep) is called."""
        from dtl import cmd_workflow_run

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        # Single-provider chain so it's immediately exhausted on first quota hit
        project_dir = self._make_project(tmp_path / "proj", provider_chain=["claude"])
        args = self._make_args(project_dir, quota_reset_sleep=999)

        sleep_calls: list[float] = []
        ai_call_count = [0]

        def fake_subprocess_run(cmd, **kwargs):
            if isinstance(cmd, list) and "--feature-name" in cmd:
                ai_call_count[0] += 1
                if ai_call_count[0] == 1:
                    return MagicMock(
                        returncode=1,
                        stdout="<<<DTL:OUTCOME=INTERRUPTED_QUOTA>>>\n",
                        stderr="",
                    )
                raise SystemExit(0)
            return MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("dtl._git_is_dirty", return_value=False),
            patch("dtl._git_create_branch"),
            patch(
                "dtl._handle_interruption",
                side_effect=lambda *a, **kw: self._fake_handle_interruption(*a, **kw),
            ),
            patch("dtl.subprocess.run", side_effect=fake_subprocess_run),
            patch("dtl.time.sleep", side_effect=lambda s: sleep_calls.append(s)),
            patch("dtl._setup_workflow_logger", return_value=MagicMock()),
            patch("dtl._preflight_auto_merge", return_value=None),
        ):
            with pytest.raises(SystemExit):
                cmd_workflow_run(args)

        assert 999 in sleep_calls, (
            f"Expected quota_reset_sleep=999 in sleep calls; got {sleep_calls}"
        )

    def test_chain_resets_after_exhaustion(self, tmp_path, monkeypatch):
        """After chain exhaustion + sleep, the chain index resets to 0."""
        from dtl import cmd_workflow_run

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = self._make_project(tmp_path / "proj", provider_chain=["claude", "ollama"])
        args = self._make_args(project_dir, quota_reset_sleep=1)

        call_providers: list[str | None] = []
        ai_call_count = [0]

        def fake_subprocess_run(cmd, **kwargs):
            if isinstance(cmd, list) and "--feature-name" in cmd:
                try:
                    idx = cmd.index("--provider")
                    call_providers.append(cmd[idx + 1])
                except ValueError:
                    call_providers.append(None)
                ai_call_count[0] += 1
                if ai_call_count[0] <= 2:
                    # Both chain members hit quota → exhaustion on second hit
                    return MagicMock(
                        returncode=1,
                        stdout="<<<DTL:OUTCOME=INTERRUPTED_QUOTA>>>\n",
                        stderr="",
                    )
                # Third call: stop the loop (chain has reset to index 0)
                raise SystemExit(0)
            return MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("dtl._git_is_dirty", return_value=False),
            patch("dtl._git_create_branch"),
            patch(
                "dtl._handle_interruption",
                side_effect=lambda *a, **kw: self._fake_handle_interruption(*a, **kw),
            ),
            patch("dtl.subprocess.run", side_effect=fake_subprocess_run),
            patch("dtl.time.sleep"),
            patch("dtl._setup_workflow_logger", return_value=MagicMock()),
            patch("dtl._preflight_auto_merge", return_value=None),
        ):
            with pytest.raises(SystemExit):
                cmd_workflow_run(args)

        # claude → ollama (chain exhausted, sleep) → claude again (chain reset)
        assert len(call_providers) == 3, f"Expected 3 AI calls; got {call_providers}"
        assert call_providers[0] == "claude"
        assert call_providers[1] == "ollama"
        assert call_providers[2] == "claude"


# ---------------------------------------------------------------------------
# Install staleness guard
# ---------------------------------------------------------------------------


class TestInstallFreshnessGuard:
    """Tests for _check_install_freshness."""

    def test_same_content_no_exception(self, tmp_path):
        """Identical file contents → returns without error."""
        content = b"# dtl source\nprint('hello')\n"
        running = tmp_path / "running_dtl.py"
        source = tmp_path / "Projects" / "devtools" / "dtl.py"
        source.parent.mkdir(parents=True)
        running.write_bytes(content)
        source.write_bytes(content)

        import dtl as dtl_module

        def fake_home():
            return tmp_path

        with (
            patch("sys.argv", [str(running)]),
            patch.object(dtl_module.Path, "home", staticmethod(fake_home)),
        ):
            # Should not raise or exit
            _check_install_freshness(schedule_mode=False)
            _check_install_freshness(schedule_mode=True)

    def test_different_content_warn_mode(self, tmp_path, capsys):
        """Different content + schedule_mode=False → warning on stderr, no exit."""
        running = tmp_path / "running_dtl.py"
        source = tmp_path / "Projects" / "devtools" / "dtl.py"
        source.parent.mkdir(parents=True)
        running.write_bytes(b"old content")
        source.write_bytes(b"new content")

        import dtl as dtl_module

        def fake_home():
            return tmp_path

        with (
            patch("sys.argv", [str(running)]),
            patch.object(dtl_module.Path, "home", staticmethod(fake_home)),
        ):
            _check_install_freshness(schedule_mode=False)

        captured = capsys.readouterr()
        assert "stale" in captured.err

    def test_different_content_schedule_mode_exits(self, tmp_path):
        """Different content + schedule_mode=True → SystemExit(1)."""
        running = tmp_path / "running_dtl.py"
        source = tmp_path / "Projects" / "devtools" / "dtl.py"
        source.parent.mkdir(parents=True)
        running.write_bytes(b"old content")
        source.write_bytes(b"new content")

        import dtl as dtl_module

        def fake_home():
            return tmp_path

        with (
            patch("sys.argv", [str(running)]),
            patch.object(dtl_module.Path, "home", staticmethod(fake_home)),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _check_install_freshness(schedule_mode=True)
        assert exc_info.value.code == 1

    def test_source_of_truth_missing_returns_silently(self, tmp_path):
        """Source-of-truth path does not exist → returns without error."""
        running = tmp_path / "running_dtl.py"
        running.write_bytes(b"some content")
        # Do NOT create the source-of-truth file

        import dtl as dtl_module

        def fake_home():
            return tmp_path  # tmp_path / Projects / devtools / dtl.py won't exist

        with (
            patch("sys.argv", [str(running)]),
            patch.object(dtl_module.Path, "home", staticmethod(fake_home)),
        ):
            # Should return silently, no exception
            _check_install_freshness(schedule_mode=False)
            _check_install_freshness(schedule_mode=True)

    def test_running_from_repo_returns_silently(self, tmp_path):
        """sys.argv[0] resolves to the source-of-truth path → returns silently."""
        source = tmp_path / "Projects" / "devtools" / "dtl.py"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"canonical content")

        import dtl as dtl_module

        def fake_home():
            return tmp_path

        # Point sys.argv[0] at the same file as source_of_truth
        with (
            patch("sys.argv", [str(source)]),
            patch.object(dtl_module.Path, "home", staticmethod(fake_home)),
        ):
            # Both paths resolve to the same file → immediate return
            _check_install_freshness(schedule_mode=False)
            _check_install_freshness(schedule_mode=True)


class TestGhPrChecks:
    """_gh_pr_checks summarises a PR's check rollup into a wait/abandon decision."""

    def _run(self, stdout: str, returncode: int = 0):
        from dtl import _gh_pr_checks

        with patch(
            "dtl.subprocess.run",
            return_value=MagicMock(returncode=returncode, stdout=stdout, stderr=""),
        ):
            return _gh_pr_checks(Path("/tmp/proj"), "feature/x")

    def test_failure_conclusion_reports_failing_with_names(self):
        rollup = json.dumps(
            [
                {"name": "lint-and-test", "status": "COMPLETED", "conclusion": "FAILURE"},
                {"name": "shellcheck", "status": "COMPLETED", "conclusion": "SUCCESS"},
            ]
        )
        state, failing = self._run(rollup)
        assert state == "FAILING"
        assert failing == ["lint-and-test"]

    def test_all_success_reports_passing(self):
        rollup = json.dumps(
            [
                {"name": "lint-and-test", "status": "COMPLETED", "conclusion": "SUCCESS"},
                {"name": "ci-ok", "status": "COMPLETED", "conclusion": "SUCCESS"},
            ]
        )
        assert self._run(rollup) == ("PASSING", [])

    def test_in_progress_check_reports_pending(self):
        rollup = json.dumps(
            [
                {"name": "lint-and-test", "status": "IN_PROGRESS", "conclusion": None},
                {"name": "ci-ok", "status": "COMPLETED", "conclusion": "SUCCESS"},
            ]
        )
        assert self._run(rollup) == ("PENDING", [])

    def test_skipped_and_neutral_do_not_block(self):
        rollup = json.dumps(
            [
                {"name": "optional", "status": "COMPLETED", "conclusion": "SKIPPED"},
                {"name": "advisory", "status": "COMPLETED", "conclusion": "NEUTRAL"},
            ]
        )
        assert self._run(rollup) == ("PASSING", [])

    def test_status_context_entries_are_understood(self):
        """A rollup may contain StatusContext (state) rather than CheckRun entries."""
        rollup = json.dumps([{"context": "legacy/ci", "state": "FAILURE"}])
        state, failing = self._run(rollup)
        assert state == "FAILING"
        assert failing == ["legacy/ci"]

    def test_empty_rollup_is_pending_not_passing(self):
        """No checks reported yet must not be mistaken for success."""
        assert self._run("[]") == ("PENDING", [])
        assert self._run("null") == ("PENDING", [])

    def test_gh_failure_is_unknown_so_a_blip_never_abandons_a_pr(self):
        assert self._run("", returncode=1) == ("UNKNOWN", [])
        assert self._run("not json") == ("UNKNOWN", [])


class TestMergeWaitTerminates:
    """Regression: a red-CI PR stays OPEN forever and used to hang the whole batch.

    Before this fix the poll loop broke only on MERGED or CLOSED, so one failing
    check starved every remaining feature (atrade 2026-09-01, PR #7).
    """

    def _make_project(self, tmp_path: Path) -> Path:
        plan = """\
# Development Plan: Test

## Feature: beta-feature

**Branch:** `feature/beta-feature`
**Depends on:** none
**Status:** Not Started

### Goal

Beta goal.

### Acceptance Criteria

- [ ] Beta criterion
"""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "DEVPLAN.md").write_text(plan)
        return tmp_path

    def _args(self, project_dir: Path):
        args = MagicMock()
        args.projects = str(project_dir)
        args.schedule = None
        args.max_failures = 3
        args.max_wall_clock = 1800
        args.max_ai_retries = 3
        args.log = None
        return args

    def _run_loop(self, tmp_path, monkeypatch, checks_return, monotonic=None):
        from dtl import cmd_workflow_run

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = self._make_project(tmp_path / "myproject")
        plan_path = project_dir / "docs" / "DEVPLAN.md"

        emitted: list[dict] = []

        def fake_emit(cfg, event_type, payload, log):
            emitted.append({"event": event_type, **payload})

        stack = [
            patch("dtl._git_is_dirty", return_value=False),
            patch("dtl._git_create_branch"),
            patch("dtl._setup_workflow_logger", return_value=MagicMock()),
            patch(
                "dtl._load_notify_config",
                return_value={"url": "https://example.com", "events": []},
            ),
            patch("dtl._emit_notify_event", side_effect=fake_emit),
            patch(
                "dtl.subprocess.run",
                return_value=MagicMock(returncode=0, stdout="", stderr=""),
            ),
            patch("dtl.ai_run"),
            patch("dtl._run_lint_and_tests", return_value=(True, "")),
            patch("dtl._git_push_branch", return_value=True),
            patch("dtl._gh_create_pr", return_value="https://github.com/org/repo/pull/7"),
            patch("dtl._gh_enable_auto_merge", return_value=True),
            # The PR never merges and is never closed -- the hang condition.
            patch("dtl._gh_pr_state", return_value="OPEN"),
            patch("dtl._gh_pr_checks", return_value=checks_return),
            patch("dtl.time.sleep"),
        ]
        if monotonic is not None:
            stack.append(patch("dtl.time.monotonic", side_effect=monotonic))

        with contextlib.ExitStack() as es:
            for ctx in stack:
                es.enter_context(ctx)
            cmd_workflow_run(self._args(project_dir))

        return emitted, plan_path.read_text()

    def test_red_ci_breaks_the_wait_and_marks_the_feature_blocked(self, tmp_path, monkeypatch):
        emitted, plan_text = self._run_loop(tmp_path, monkeypatch, ("FAILING", ["lint-and-test"]))

        assert "**Status:** Blocked (CI red" in plan_text
        assert "lint-and-test" in plan_text
        ci_failed = [e for e in emitted if e["event"] == "ci-failed"]
        assert ci_failed, f"Expected a ci-failed event; got {emitted}"
        assert ci_failed[0]["failing_checks"] == ["lint-and-test"]

    def test_pending_forever_gives_up_at_the_deadline(self, tmp_path, monkeypatch):
        """Checks that never complete must not wait past MERGE_WAIT_TIMEOUT_S."""
        import dtl

        # A clock that advances a full timeout per call. time.monotonic is consulted
        # in several places in the loop, so we cannot assume which call sets the
        # deadline -- an always-advancing clock guarantees the deadline is passed
        # whichever call it was, without ever exhausting.
        clock = {"t": 0.0}

        def fake_monotonic() -> float:
            clock["t"] += float(dtl.MERGE_WAIT_TIMEOUT_S)
            return clock["t"]

        emitted, plan_text = self._run_loop(
            tmp_path, monkeypatch, ("PENDING", []), monotonic=fake_monotonic
        )

        assert "**Status:** Blocked (merge wait timed out" in plan_text
        assert [e for e in emitted if e["event"] == "merge-timeout"], (
            f"Expected a merge-timeout event; got {emitted}"
        )
