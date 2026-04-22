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
    _maybe_notify_stalled,
    _parse_devplan,
    _read_workflow_state,
    _run_lint_and_tests,
    _update_feature_status,
    _workflow_state_path,
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
        skip_calls = [
            c for c in mock_logger.info.call_args_list if "dirty" in str(c).lower()
        ]
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
        dirty_responses = iter(
            [False]
        )  # clean on first real check; will raise StopIteration after

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
            _maybe_notify_stalled(
                project_dir, "dirty_tree", WORKFLOW_STALL_THRESHOLD, MagicMock()
            )

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
        args.project = str(project_dir)
        cmd_workflow_status(args)

        out = capsys.readouterr().out
        assert "No workflow state" in out

    def test_prints_state_when_file_present(self, tmp_path, monkeypatch, capsys):
        from dtl import cmd_workflow_status

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project_dir = self._make_project(tmp_path / "proj")

        _write_workflow_state(project_dir, "dirty_tree", 2)

        args = MagicMock()
        args.project = str(project_dir)
        cmd_workflow_status(args)

        out = capsys.readouterr().out
        assert "dirty_tree" in out
        assert "2" in out
        assert "proj" in out


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
