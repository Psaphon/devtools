"""Tests for dtl workflow finish/run: PR creation, merge polling, loop logic."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from dtl import (
    _detect_auth_failure,
    _find_feature_for_branch,
    _parse_devplan,
    _run_lint_and_tests,
    _setup_workflow_logger,
    cmd_workflow_finish,
)

# ---------------------------------------------------------------------------
# Sample DEVPLAN fixture
# ---------------------------------------------------------------------------

SAMPLE_PLAN = """\
# Development Plan: Test Project

**Status:** In Progress

## Constraints

- Single file, stdlib-only
- Must work offline

---

## Feature: alpha-feature

**Branch:** `feature/alpha-feature`
**Depends on:** none
**Status:** Merged

### Goal

Alpha goal.

---

## Feature: beta-feature

**Branch:** `feature/beta-feature`
**Depends on:** alpha-feature
**Status:** In Progress

### Goal

Beta goal description here.

### Acceptance Criteria

- [ ] Beta criterion

---

## Feature: gamma-feature

**Branch:** `feature/gamma-feature`
**Depends on:** beta-feature
**Status:** Not Started

### Goal

Gamma goal.
"""


# ---------------------------------------------------------------------------
# _detect_auth_failure
# ---------------------------------------------------------------------------


class TestDetectAuthFailure:
    def test_detects_auth_error(self):
        assert _detect_auth_failure("Error: Authentication failed for Claude API")

    def test_detects_login_prompt(self):
        assert _detect_auth_failure("Please run claude login to authenticate")

    def test_detects_expired_token(self):
        assert _detect_auth_failure("Your session has expired token please re-auth")

    def test_normal_output_not_flagged(self):
        assert not _detect_auth_failure("Successfully implemented the feature")

    def test_empty_output(self):
        assert not _detect_auth_failure("")

    def test_case_insensitive(self):
        assert _detect_auth_failure("UNAUTHORIZED access denied")


# ---------------------------------------------------------------------------
# _find_feature_for_branch
# ---------------------------------------------------------------------------


class TestFindFeatureForBranch:
    def test_finds_matching_feature(self):
        _, features = _parse_devplan(SAMPLE_PLAN)
        result = _find_feature_for_branch(features, "feature/beta-feature")
        assert result is not None
        assert result["name"] == "beta-feature"

    def test_returns_none_for_unknown_branch(self):
        _, features = _parse_devplan(SAMPLE_PLAN)
        result = _find_feature_for_branch(features, "feature/nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# _run_lint_and_tests
# ---------------------------------------------------------------------------


class TestRunLintAndTests:
    def test_python_project_detected(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")
        with patch("dtl.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            passed, output = _run_lint_and_tests(tmp_path)
        assert passed
        assert mock_run.call_count == 3  # pip install + lint + test

    def test_lint_failure_stops_early(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")

        def fake_run(cmd, **kwargs):
            if "pip" in " ".join(str(c) for c in cmd):
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="lint error")

        with patch("dtl.subprocess.run", side_effect=fake_run):
            passed, output = _run_lint_and_tests(tmp_path)
        assert not passed
        assert "lint error" in output

    def test_no_project_files(self, tmp_path):
        passed, output = _run_lint_and_tests(tmp_path)
        assert passed  # nothing to check = pass

    def test_node_project_detected(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        with patch("dtl.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            passed, _ = _run_lint_and_tests(tmp_path)
        assert passed
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert calls[0] == ["npm", "run", "lint"]
        assert calls[1] == ["npm", "test"]


# ---------------------------------------------------------------------------
# _setup_workflow_logger
# ---------------------------------------------------------------------------


class TestSetupWorkflowLogger:
    def test_creates_log_file(self, tmp_path):
        log_path = tmp_path / "test.log"
        logger = _setup_workflow_logger(log_path)
        logger.info("test message")
        # Force flush
        for h in logger.handlers:
            h.flush()
        assert log_path.exists()
        assert "test message" in log_path.read_text()
        # Clean up handlers to avoid leaking between tests
        logger.handlers.clear()


# ---------------------------------------------------------------------------
# cmd_workflow_finish
# ---------------------------------------------------------------------------


class TestCmdWorkflowFinish:
    def _make_project(self, tmp_path):
        plan_file = tmp_path / "docs" / "DEVPLAN.md"
        plan_file.parent.mkdir(parents=True, exist_ok=True)
        plan_file.write_text(SAMPLE_PLAN)
        return plan_file

    def test_exits_on_missing_plan(self, tmp_path):
        args = MagicMock()
        args.plan = str(tmp_path / "nonexistent.md")
        args.project = str(tmp_path)
        args.watch = False
        with pytest.raises(SystemExit) as exc:
            cmd_workflow_finish(args)
        assert exc.value.code == 1

    def test_exits_when_branch_not_in_plan(self, tmp_path):
        plan_file = self._make_project(tmp_path)
        args = MagicMock()
        args.plan = str(plan_file)
        args.project = str(tmp_path)
        args.watch = False

        with patch("dtl._git_current_branch", return_value="feature/unknown"):
            with pytest.raises(SystemExit) as exc:
                cmd_workflow_finish(args)
            assert exc.value.code == 1

    def test_aborts_on_test_failure(self, tmp_path):
        plan_file = self._make_project(tmp_path)
        args = MagicMock()
        args.plan = str(plan_file)
        args.project = str(tmp_path)
        args.watch = False

        with (
            patch("dtl._git_current_branch", return_value="feature/beta-feature"),
            patch("dtl._run_lint_and_tests", return_value=(False, "test failed")),
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_workflow_finish(args)
            assert exc.value.code == 1

        # Status should be updated to Failed
        _, features = _parse_devplan(plan_file.read_text())
        beta = next(f for f in features if f["name"] == "beta-feature")
        assert beta["status"] == "Failed"

    def test_happy_path_creates_pr(self, tmp_path):
        plan_file = self._make_project(tmp_path)
        args = MagicMock()
        args.plan = str(plan_file)
        args.project = str(tmp_path)
        args.watch = False

        with (
            patch("dtl._git_current_branch", return_value="feature/beta-feature"),
            patch("dtl._run_lint_and_tests", return_value=(True, "all passed")),
            patch("dtl._git_is_dirty", return_value=False),
            patch("dtl._git_push_branch", return_value=True),
            patch(
                "dtl._gh_create_pr", return_value="https://github.com/test/pr/1"
            ) as mock_pr,
            patch("dtl.subprocess.run"),  # for git add/commit/push of status
        ):
            cmd_workflow_finish(args)

        mock_pr.assert_called_once()
        # Status should be PR Open
        _, features = _parse_devplan(plan_file.read_text())
        beta = next(f for f in features if f["name"] == "beta-feature")
        assert beta["status"] == "PR Open"

    def test_exits_on_push_failure(self, tmp_path):
        plan_file = self._make_project(tmp_path)
        args = MagicMock()
        args.plan = str(plan_file)
        args.project = str(tmp_path)
        args.watch = False

        with (
            patch("dtl._git_current_branch", return_value="feature/beta-feature"),
            patch("dtl._run_lint_and_tests", return_value=(True, "ok")),
            patch("dtl._git_is_dirty", return_value=False),
            patch("dtl._git_push_branch", return_value=False),
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_workflow_finish(args)
            assert exc.value.code == 1
