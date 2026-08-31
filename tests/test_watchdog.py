"""Tests for dtl watchdog anomaly detection."""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import dtl

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_DEVPLAN_TEMPLATE = """\
# Development Plan: {name}

## Overview

Test.

## Constraints

- None

{features}
"""

FEATURE_TEMPLATE = """\
## Feature: feature-{i}

**Branch:** `feature/feature-{i}`
**Depends on:** none
**Status:** {status}

### Goal

Test feature {i}.

### Acceptance Criteria

- [ ] Something

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `test.py` | Create | Test |
"""


def make_project(tmp_path: Path, name: str = "myproject") -> Path:
    """Create a minimal fake project directory."""
    project = tmp_path / name
    project.mkdir()
    (project / ".git").mkdir()
    (project / "docs").mkdir()
    return project


def write_devplan(project: Path, statuses: list[str]) -> None:
    """Write a DEVPLAN.md with features at the given statuses."""
    features = "\n".join(
        FEATURE_TEMPLATE.format(i=i, status=s) for i, s in enumerate(statuses)
    )
    plan_text = SAMPLE_DEVPLAN_TEMPLATE.format(name=project.name, features=features)
    (project / "docs" / "DEVPLAN.md").write_text(plan_text)


# ---------------------------------------------------------------------------
# Check A: missing workflow runner
# ---------------------------------------------------------------------------


class TestWatchdogCheckMissingRunner:
    def test_no_devplan_returns_none(self, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        assert dtl._watchdog_check_missing_runner(project) is None

    def test_all_features_done_returns_none(self, tmp_path):
        project = make_project(tmp_path)
        write_devplan(project, ["Merged", "Merged"])
        assert dtl._watchdog_check_missing_runner(project) is None

    def test_not_started_no_process_returns_anomaly(self, tmp_path):
        project = make_project(tmp_path)
        write_devplan(project, ["Not Started", "Merged"])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="other stuff\n", returncode=0)
            result = dtl._watchdog_check_missing_runner(project)
        assert result is not None
        assert "Not Started" in result
        assert project.name in result

    def test_not_started_with_matching_process_returns_none(self, tmp_path):
        project = make_project(tmp_path)
        write_devplan(project, ["Not Started"])
        fake_ps = (
            f"user 1234 0.0 0.1 python3 dtl.py workflow run --projects {project}\n"
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_ps, returncode=0)
            result = dtl._watchdog_check_missing_runner(project)
        assert result is None

    def test_ps_failure_does_not_raise(self, tmp_path):
        project = make_project(tmp_path)
        write_devplan(project, ["Not Started"])
        with patch("subprocess.run", side_effect=Exception("ps unavailable")):
            # Should still detect missing runner (exception is swallowed).
            result = dtl._watchdog_check_missing_runner(project)
        assert result is not None

    def test_state_file_quota_interruption_suppresses_anomaly(
        self, tmp_path, monkeypatch
    ):
        """If the feature state shows INTERRUPTED_QUOTA, the watchdog suppresses
        anomaly A because the workflow halted intentionally for human attention."""
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project = make_project(tmp_path)
        write_devplan(project, ["Not Started"])

        # Write per-feature state showing intentional halt
        dtl._write_feature_state(
            project,
            "feature-0",
            {
                "last_outcome": dtl.RunOutcome.INTERRUPTED_QUOTA,
                "last_run_iso": "2026-05-16T00:00:00+00:00",
                "attempts_completed": 0,
                "attempts_interrupted": 1,
                "partial_work_branch": None,
            },
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="other stuff\n", returncode=0)
            result = dtl._watchdog_check_missing_runner(project)
        assert result is None, (
            "INTERRUPTED_QUOTA state should suppress missing-runner anomaly"
        )

    def test_state_file_auth_interruption_suppresses_anomaly(
        self, tmp_path, monkeypatch
    ):
        """INTERRUPTED_AUTH also suppresses anomaly A."""
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project = make_project(tmp_path)
        write_devplan(project, ["Not Started"])

        dtl._write_feature_state(
            project,
            "feature-0",
            {
                "last_outcome": dtl.RunOutcome.INTERRUPTED_AUTH,
                "last_run_iso": "2026-05-16T00:00:00+00:00",
                "attempts_completed": 0,
                "attempts_interrupted": 1,
                "partial_work_branch": None,
            },
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="other stuff\n", returncode=0)
            result = dtl._watchdog_check_missing_runner(project)
        assert result is None, (
            "INTERRUPTED_AUTH state should suppress missing-runner anomaly"
        )

    def test_state_file_failed_ai_does_not_suppress_anomaly(
        self, tmp_path, monkeypatch
    ):
        """FAILED_AI state does not suppress anomaly A — the workflow should retry."""
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        project = make_project(tmp_path)
        write_devplan(project, ["Not Started"])

        dtl._write_feature_state(
            project,
            "feature-0",
            {
                "last_outcome": dtl.RunOutcome.FAILED_AI,
                "last_run_iso": "2026-05-16T00:00:00+00:00",
                "attempts_completed": 1,
                "attempts_interrupted": 0,
                "partial_work_branch": None,
            },
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="other stuff\n", returncode=0)
            result = dtl._watchdog_check_missing_runner(project)
        assert result is not None, (
            "FAILED_AI state should NOT suppress missing-runner anomaly"
        )

    # ------------------------------------------------------------------
    # Which running workflow actually covers this project.
    #
    # The check used to test the whole `ps` line for the project path as a
    # substring. Every 'dtl workflow run' command line contains the path to
    # dtl.py itself, so a run for ANY project silently marked the repo hosting
    # dtl.py as covered — observed live on 2026-08-31, where arming a run for
    # atrade made devtools' real anomaly disappear.
    # ------------------------------------------------------------------

    def test_dtl_py_location_in_cmdline_does_not_count_as_coverage(self, tmp_path):
        """A run for another project must not cover the repo hosting dtl.py."""
        devtools = make_project(tmp_path, name="devtools")
        write_devplan(devtools, ["Not Started"])
        atrade = tmp_path / "atrade"
        atrade.mkdir()
        # The real shape: dtl.py lives in devtools, the run targets atrade.
        fake_ps = (
            f"user 1234 0.0 0.1 python3 {devtools}/dtl.py workflow run "
            f"--projects {atrade} --schedule 02:00\n"
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_ps, returncode=0)
            result = dtl._watchdog_check_missing_runner(devtools)
        assert result is not None, (
            "devtools has Not Started work and no run of its own — the presence "
            "of its path as the dtl.py location must not suppress the anomaly"
        )

    def test_project_named_in_projects_list_counts_as_coverage(self, tmp_path):
        """The targeted project itself is still correctly considered covered."""
        devtools = make_project(tmp_path, name="devtools")
        atrade = make_project(tmp_path, name="atrade")
        write_devplan(atrade, ["Not Started"])
        fake_ps = (
            f"user 1234 0.0 0.1 python3 {devtools}/dtl.py workflow run "
            f"--projects {atrade} --schedule 02:00\n"
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_ps, returncode=0)
            result = dtl._watchdog_check_missing_runner(atrade)
        assert result is None

    def test_multi_project_run_covers_each_listed_project(self, tmp_path):
        """A comma-separated --projects list covers every entry."""
        devtools = make_project(tmp_path, name="devtools")
        loom = make_project(tmp_path, name="loom")
        atrade = make_project(tmp_path, name="atrade")
        write_devplan(loom, ["Not Started"])
        fake_ps = (
            f"user 1234 0.0 0.1 python3 {devtools}/dtl.py workflow run "
            f"--projects {atrade},{loom}\n"
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_ps, returncode=0)
            result = dtl._watchdog_check_missing_runner(loom)
        assert result is None

    def test_trailing_slash_and_dot_segments_still_match(self, tmp_path):
        """Path spelling differences must not create a false anomaly."""
        loom = make_project(tmp_path, name="loom")
        write_devplan(loom, ["Not Started"])
        odd = f"{tmp_path}/./loom/"
        fake_ps = f"user 1 0.0 0.1 python3 dtl.py workflow run --projects {odd}\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_ps, returncode=0)
            result = dtl._watchdog_check_missing_runner(loom)
        assert result is None

    def test_run_without_projects_flag_is_not_coverage(self, tmp_path):
        """A 'workflow run' line with no --projects argument covers nothing."""
        loom = make_project(tmp_path, name="loom")
        write_devplan(loom, ["Not Started"])
        fake_ps = f"user 1 0.0 0.1 python3 {loom}/dtl.py workflow run --help\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_ps, returncode=0)
            result = dtl._watchdog_check_missing_runner(loom)
        assert result is not None


# ---------------------------------------------------------------------------
# Check B: dirty tree age
# ---------------------------------------------------------------------------


class TestWatchdogCheckDirtyAge:
    def test_clean_tree_returns_none(self, tmp_path):
        project = make_project(tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            result = dtl._watchdog_check_dirty_age(project)
        assert result is None

    def test_recently_dirty_file_returns_none(self, tmp_path):
        project = make_project(tmp_path)
        dirty_file = project / "new.py"
        dirty_file.write_text("x = 1")
        # mtime defaults to now — well within threshold
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=" M new.py\n", returncode=0)
            result = dtl._watchdog_check_dirty_age(project)
        assert result is None

    def test_old_dirty_file_returns_anomaly(self, tmp_path):
        project = make_project(tmp_path)
        dirty_file = project / "old.py"
        dirty_file.write_text("x = 1")
        # Back-date mtime by 25 hours.
        old_time = time.time() - (25 * 3600)
        os.utime(dirty_file, (old_time, old_time))
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=" M old.py\n", returncode=0)
            result = dtl._watchdog_check_dirty_age(project)
        assert result is not None
        assert "dirty" in result.lower()
        assert project.name in result

    def test_rename_entry_parsed_correctly(self, tmp_path):
        """Porcelain rename lines like 'R  old -> new' should not crash."""
        project = make_project(tmp_path)
        new_file = project / "new.py"
        new_file.write_text("x = 1")
        old_time = time.time() - (25 * 3600)
        os.utime(new_file, (old_time, old_time))
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="R  old.py -> new.py\n", returncode=0
            )
            # Should not raise; may or may not detect anomaly depending on file existence.
            dtl._watchdog_check_dirty_age(project)

    def test_threshold_boundary(self, tmp_path):
        """A file exactly at the threshold (24 h) triggers the anomaly."""
        project = make_project(tmp_path)
        dirty_file = project / "boundary.py"
        dirty_file.write_text("x = 1")
        boundary_time = time.time() - (dtl.WATCHDOG_DIRTY_HOURS * 3600)
        os.utime(dirty_file, (boundary_time, boundary_time))
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=" M boundary.py\n", returncode=0)
            result = dtl._watchdog_check_dirty_age(project)
        assert result is not None


# ---------------------------------------------------------------------------
# Check C: PR activity
# ---------------------------------------------------------------------------


class TestWatchdogCheckPrActivity:
    def test_no_devplan_returns_none(self, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        assert dtl._watchdog_check_pr_activity(project) is None

    def test_no_not_started_features_returns_none(self, tmp_path):
        project = make_project(tmp_path)
        write_devplan(project, ["Merged", "Merged"])
        assert dtl._watchdog_check_pr_activity(project) is None

    def test_recent_pr_activity_returns_none(self, tmp_path):
        project = make_project(tmp_path)
        write_devplan(project, ["Not Started"])
        recent = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        ).isoformat()
        prs = [{"number": 1, "updatedAt": recent}]
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(prs), returncode=0)
            result = dtl._watchdog_check_pr_activity(project)
        assert result is None

    def test_recent_pr_activity_with_github_z_suffix_timestamp(self, tmp_path):
        """GitHub returns '...Z', not '...+00:00' — parse the real wire format.

        The other tests in this class build timestamps with
        `datetime.now(tz).isoformat()`, which yields a '+00:00' offset. The
        `gh pr list --json updatedAt` API actually returns a 'Z' suffix, so
        those tests never exercised the format this code really receives.

        The parse is wrapped in `except (ValueError, AttributeError): pass`, so
        a failure is SILENT and FAILS OPEN: every PR is skipped, `most_recent`
        stays None, the staleness branch is never reached, and the function
        returns None. The watchdog would stop reporting stale PRs entirely —
        a false negative, which is the worse direction for a watchdog to fail.

        This case alone cannot detect that (it also expects None), which is why
        it is paired with the stale-timestamp test below; that one does.
        """
        recent = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            hours=1
        )
        # Explicitly the GitHub wire format: trailing Z, no offset.
        z_stamp = recent.strftime("%Y-%m-%dT%H:%M:%SZ")
        assert z_stamp.endswith("Z")

        project = make_project(tmp_path)
        write_devplan(project, ["Not Started"])
        prs = [{"number": 1, "updatedAt": z_stamp}]
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(prs), returncode=0)
            result = dtl._watchdog_check_pr_activity(project)
        assert result is None, (
            "a Z-suffixed timestamp one hour old must count as recent activity; "
            "if this fails the timestamp did not parse and every PR was skipped"
        )

    def test_stale_pr_with_github_z_suffix_timestamp(self, tmp_path):
        """A stale Z-suffixed timestamp must still raise the anomaly.

        This is the case with teeth. If the Z format stops parsing, every PR is
        skipped, `most_recent` stays None, and the function returns None — so
        this assertion fails where the recent-timestamp case would not.
        Verified by mutation: breaking the parse fails this test and only this
        test.
        """
        stale = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            hours=60
        )
        z_stamp = stale.strftime("%Y-%m-%dT%H:%M:%SZ")

        project = make_project(tmp_path)
        write_devplan(project, ["Not Started"])
        prs = [{"number": 1, "updatedAt": z_stamp}]
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(prs), returncode=0)
            result = dtl._watchdog_check_pr_activity(project)
        assert result is not None
        assert "PR activity" in result

    def test_stale_pr_with_not_started_returns_anomaly(self, tmp_path):
        project = make_project(tmp_path)
        write_devplan(project, ["Not Started"])
        stale = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=60)
        ).isoformat()
        prs = [{"number": 1, "updatedAt": stale}]
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(prs), returncode=0)
            result = dtl._watchdog_check_pr_activity(project)
        assert result is not None
        assert "PR activity" in result
        assert project.name in result

    def test_gh_failure_returns_none(self, tmp_path):
        """When gh is unavailable, the check is skipped gracefully."""
        project = make_project(tmp_path)
        write_devplan(project, ["Not Started"])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=1)
            result = dtl._watchdog_check_pr_activity(project)
        assert result is None

    def test_in_progress_no_prs_returns_anomaly(self, tmp_path):
        """In Progress features with no open PRs should also be flagged."""
        project = make_project(tmp_path)
        write_devplan(project, ["Not Started", "In Progress"])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="[]", returncode=0)
            result = dtl._watchdog_check_pr_activity(project)
        assert result is not None


# ---------------------------------------------------------------------------
# Check D: log growth
# ---------------------------------------------------------------------------


class TestWatchdogCheckLogGrowth:
    def test_no_previous_state_returns_no_anomaly(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dtl, "_dtl_state_dir", lambda: tmp_path)
        anomaly, _ = dtl._watchdog_check_log_growth({})
        assert anomaly is None

    def test_slow_growth_returns_no_anomaly(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dtl, "_dtl_state_dir", lambda: tmp_path)
        log_file = tmp_path / "test.log"
        log_file.write_bytes(b"x" * 1024)  # 1 KB total
        prev_state = {
            "log_size_bytes": 512,
            "log_size_timestamp": (
                datetime.datetime.now() - datetime.timedelta(hours=24)
            ).isoformat(),
        }
        anomaly, _ = dtl._watchdog_check_log_growth(prev_state)
        assert anomaly is None

    def test_fast_growth_returns_anomaly(self, tmp_path, monkeypatch):
        """Growth above threshold triggers anomaly D."""
        monkeypatch.setattr(dtl, "_dtl_state_dir", lambda: tmp_path)
        # Lower the threshold to 0.001 MB/day so a 2 KB file triggers it.
        monkeypatch.setattr(dtl, "WATCHDOG_LOG_GROWTH_MB_DAY", 0.001)
        log_file = tmp_path / "test.log"
        log_file.write_bytes(b"x" * 2048)  # 2 KB
        prev_state = {
            "log_size_bytes": 0,
            "log_size_timestamp": (
                datetime.datetime.now() - datetime.timedelta(hours=24)
            ).isoformat(),
        }
        anomaly, _ = dtl._watchdog_check_log_growth(prev_state)
        assert anomaly is not None
        assert "MB/day" in anomaly

    def test_returns_current_bytes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dtl, "_dtl_state_dir", lambda: tmp_path)
        log_file = tmp_path / "app.log"
        log_file.write_bytes(b"x" * 4096)
        _, current = dtl._watchdog_check_log_growth({})
        assert current == 4096

    def test_missing_state_dir_returns_zero_bytes(self, tmp_path, monkeypatch):
        missing = tmp_path / "nonexistent"
        monkeypatch.setattr(dtl, "_dtl_state_dir", lambda: missing)
        anomaly, current = dtl._watchdog_check_log_growth({})
        assert anomaly is None
        assert current == 0


# ---------------------------------------------------------------------------
# _watchdog_notify_project
# ---------------------------------------------------------------------------


class TestWatchdogNotifyProject:
    def _log(self):
        return logging.getLogger("test.watchdog")

    def test_no_notify_script_does_not_raise(self, tmp_path):
        project = make_project(tmp_path)
        # No .ai/notify.py — should silently skip.
        dtl._watchdog_notify_project(project, ["an anomaly"], self._log())

    def test_notify_called_exactly_once_for_multiple_anomalies(self, tmp_path):
        """All anomalies for one project produce a single notify.py invocation."""
        project = make_project(tmp_path)
        ai_dir = project / ".ai"
        ai_dir.mkdir()
        (ai_dir / "notify.py").write_text("import sys; sys.exit(0)")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            dtl._watchdog_notify_project(
                project, ["anomaly 1", "anomaly 2", "anomaly 3"], self._log()
            )

        assert mock_run.call_count == 1
        call_args = mock_run.call_args[0][0]
        assert str(ai_dir / "notify.py") in call_args
        assert "1" in call_args  # exit-code argument

    def test_empty_anomalies_does_not_call_notify(self, tmp_path):
        project = make_project(tmp_path)
        ai_dir = project / ".ai"
        ai_dir.mkdir()
        (ai_dir / "notify.py").write_text("import sys; sys.exit(0)")

        with patch("subprocess.run") as mock_run:
            dtl._watchdog_notify_project(project, [], self._log())

        mock_run.assert_not_called()

    def test_notify_message_contains_all_anomalies(self, tmp_path):
        project = make_project(tmp_path)
        ai_dir = project / ".ai"
        ai_dir.mkdir()
        (ai_dir / "notify.py").write_text("import sys; sys.exit(0)")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            dtl._watchdog_notify_project(
                project, ["issue alpha", "issue beta"], self._log()
            )

        message = mock_run.call_args[0][0][-1]  # last positional arg is the message
        assert "issue alpha" in message
        assert "issue beta" in message

    # ------------------------------------------------------------------
    # Delivery-failure reporting.
    #
    # These deliberately run a REAL notify.py subprocess instead of patching
    # subprocess.run. The bug these cover — "notification sent" logged even when
    # notify.py exited non-zero — was invisible to every mocked test above,
    # because a MagicMock never fails the way the real script does.
    # ------------------------------------------------------------------

    def test_failing_notify_script_does_not_claim_success(self, tmp_path, caplog):
        """A notify.py that exits 1 must NOT produce a 'notification sent' line."""
        project = make_project(tmp_path)
        ai_dir = project / ".ai"
        ai_dir.mkdir()
        # Mirrors the real notify.py's no-credentials path.
        (ai_dir / "notify.py").write_text(
            "import sys\n"
            "print('[notify] Telegram not configured.', file=sys.stderr)\n"
            "sys.exit(1)\n"
        )

        with caplog.at_level(logging.INFO):
            dtl._watchdog_notify_project(project, ["an anomaly"], self._log())

        assert "Watchdog notification sent" not in caplog.text
        assert "NOT delivered" in caplog.text
        assert "exit 1" in caplog.text

    def test_failing_notify_script_surfaces_stderr(self, tmp_path, caplog):
        """The reason for the failure must reach the log, not be discarded."""
        project = make_project(tmp_path)
        ai_dir = project / ".ai"
        ai_dir.mkdir()
        (ai_dir / "notify.py").write_text(
            "import sys\nprint('missing chat_id', file=sys.stderr)\nsys.exit(1)\n"
        )

        with caplog.at_level(logging.INFO):
            dtl._watchdog_notify_project(project, ["an anomaly"], self._log())

        assert "missing chat_id" in caplog.text

    def test_successful_notify_script_still_reports_sent(self, tmp_path, caplog):
        """The success path must keep working — a real script exiting 0."""
        project = make_project(tmp_path)
        ai_dir = project / ".ai"
        ai_dir.mkdir()
        (ai_dir / "notify.py").write_text("import sys\nsys.exit(0)\n")

        with caplog.at_level(logging.INFO):
            dtl._watchdog_notify_project(project, ["a", "b"], self._log())

        assert "Watchdog notification sent (2 anomaly/anomalies)" in caplog.text
        assert "NOT delivered" not in caplog.text

    def test_watchdog_survives_notify_script_that_crashes(self, tmp_path, caplog):
        """A notify.py that raises must be reported, not swallowed as success."""
        project = make_project(tmp_path)
        ai_dir = project / ".ai"
        ai_dir.mkdir()
        (ai_dir / "notify.py").write_text("raise RuntimeError('boom')\n")

        with caplog.at_level(logging.INFO):
            dtl._watchdog_notify_project(project, ["an anomaly"], self._log())

        assert "Watchdog notification sent" not in caplog.text
        assert "NOT delivered" in caplog.text


# ---------------------------------------------------------------------------
# Unit template generators
# ---------------------------------------------------------------------------


class TestWatchdogUnitTemplates:
    def test_service_contains_project_path(self, tmp_path):
        projects = f"{tmp_path}/proj1,{tmp_path}/proj2"
        service = dtl._make_watchdog_service(projects)
        assert "watchdog check" in service
        assert projects in service
        assert "[Service]" in service
        assert "Type=oneshot" in service

    def test_timer_default_interval(self):
        timer = dtl._make_watchdog_timer(120)
        assert "120min" in timer
        assert "[Timer]" in timer
        assert "WantedBy=timers.target" in timer

    def test_timer_custom_interval(self):
        timer = dtl._make_watchdog_timer(60)
        assert "60min" in timer


# ---------------------------------------------------------------------------
# cmd_watchdog_install
# ---------------------------------------------------------------------------


class TestCmdWatchdogInstall:
    def test_writes_service_and_timer_files(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            args = argparse.Namespace(
                projects=str(tmp_path / "proj"),
                interval=120,
            )
            dtl.cmd_watchdog_install(args)

        service = tmp_path / ".config" / "systemd" / "user" / "dtl-watchdog.service"
        timer = tmp_path / ".config" / "systemd" / "user" / "dtl-watchdog.timer"
        assert service.exists()
        assert timer.exists()

    def test_service_references_check_subcommand(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            args = argparse.Namespace(
                projects=str(tmp_path / "proj"),
                interval=120,
            )
            dtl.cmd_watchdog_install(args)

        service_text = (
            tmp_path / ".config" / "systemd" / "user" / "dtl-watchdog.service"
        ).read_text()
        assert "watchdog check" in service_text

    def test_timer_uses_specified_interval(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            args = argparse.Namespace(
                projects=str(tmp_path / "proj"),
                interval=45,
            )
            dtl.cmd_watchdog_install(args)

        timer_text = (
            tmp_path / ".config" / "systemd" / "user" / "dtl-watchdog.timer"
        ).read_text()
        assert "45min" in timer_text

    def test_output_includes_activation_commands(self, tmp_path, capsys):
        with patch.object(Path, "home", return_value=tmp_path):
            args = argparse.Namespace(
                projects=str(tmp_path / "proj"),
                interval=120,
            )
            dtl.cmd_watchdog_install(args)

        out = capsys.readouterr().out
        assert "systemctl" in out
        assert "enable" in out


# ---------------------------------------------------------------------------
# cmd_watchdog_status
# ---------------------------------------------------------------------------


class TestCmdWatchdogStatus:
    def test_no_state_prints_guidance(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr(
            dtl, "_watchdog_state_path", lambda: tmp_path / "nonexistent.json"
        )
        dtl.cmd_watchdog_status(argparse.Namespace())
        out = capsys.readouterr().out
        assert "No watchdog state" in out

    def test_pass_result_is_printed(self, tmp_path, capsys, monkeypatch):
        state_file = tmp_path / "watchdog-state.json"
        state_file.write_text(
            json.dumps(
                {
                    "last_run": "2026-04-22T10:00:00",
                    "last_result": "PASS",
                    "last_anomalies": [],
                }
            )
        )
        monkeypatch.setattr(dtl, "_watchdog_state_path", lambda: state_file)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            dtl.cmd_watchdog_status(argparse.Namespace())
        out = capsys.readouterr().out
        assert "PASS" in out
        assert "2026-04-22T10:00:00" in out

    def test_anomalies_are_listed(self, tmp_path, capsys, monkeypatch):
        state_file = tmp_path / "watchdog-state.json"
        state_file.write_text(
            json.dumps(
                {
                    "last_run": "2026-04-22T10:00:00",
                    "last_result": "FAIL",
                    "last_anomalies": ["myproject: dirty tree 30h ago"],
                }
            )
        )
        monkeypatch.setattr(dtl, "_watchdog_state_path", lambda: state_file)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            dtl.cmd_watchdog_status(argparse.Namespace())
        out = capsys.readouterr().out
        assert "dirty tree" in out


# ---------------------------------------------------------------------------
# cmd_watchdog_check (integration-level)
# ---------------------------------------------------------------------------


class TestCmdWatchdogCheck:
    def test_clean_project_outputs_pass(self, tmp_path, capsys, monkeypatch):
        project = make_project(tmp_path)
        write_devplan(project, ["Merged"])
        monkeypatch.setattr(dtl, "_watchdog_state_path", lambda: tmp_path / "ws.json")
        monkeypatch.setattr(dtl, "_dtl_state_dir", lambda: tmp_path / "state")

        # Mock subprocess: clean git tree, no ps anomaly
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            args = argparse.Namespace(projects=str(project))
            dtl.cmd_watchdog_check(args)

        out = capsys.readouterr().out
        assert "PASS" in out

    def test_missing_project_dir_is_skipped(self, tmp_path, capsys, monkeypatch):
        missing = tmp_path / "nonexistent"
        monkeypatch.setattr(dtl, "_watchdog_state_path", lambda: tmp_path / "ws.json")
        monkeypatch.setattr(dtl, "_dtl_state_dir", lambda: tmp_path / "state")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            args = argparse.Namespace(projects=str(missing))
            dtl.cmd_watchdog_check(args)

        out = capsys.readouterr().out
        assert "PASS" in out  # no errors raised; missing dir is logged and skipped

    def test_anomaly_triggers_notify_and_fail(self, tmp_path, capsys, monkeypatch):
        project = make_project(tmp_path)
        write_devplan(project, ["Not Started"])
        ai_dir = project / ".ai"
        ai_dir.mkdir()
        (ai_dir / "notify.py").write_text("import sys; sys.exit(0)")

        monkeypatch.setattr(dtl, "_watchdog_state_path", lambda: tmp_path / "ws.json")
        monkeypatch.setattr(dtl, "_dtl_state_dir", lambda: tmp_path / "state")

        call_log: list[list] = []

        def fake_run(cmd, **kwargs):
            call_log.append(list(cmd))
            if "ps" in cmd:
                return MagicMock(stdout="other stuff\n", returncode=0)
            if "git" in cmd:
                return MagicMock(stdout="", returncode=0)
            if "gh" in cmd:
                return MagicMock(stdout="[]", returncode=0)
            # notify.py invocation
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            args = argparse.Namespace(projects=str(project))
            dtl.cmd_watchdog_check(args)

        out = capsys.readouterr().out
        assert "FAIL" in out

        # Exactly one notify.py call for the project
        notify_calls = [c for c in call_log if "notify.py" in " ".join(c)]
        assert len(notify_calls) == 1

    def test_state_is_written_after_check(self, tmp_path, monkeypatch):
        project = make_project(tmp_path)
        write_devplan(project, ["Merged"])
        state_file = tmp_path / "ws.json"
        monkeypatch.setattr(dtl, "_watchdog_state_path", lambda: state_file)
        monkeypatch.setattr(dtl, "_dtl_state_dir", lambda: tmp_path / "state")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            args = argparse.Namespace(projects=str(project))
            dtl.cmd_watchdog_check(args)

        assert state_file.exists()
        state = json.loads(state_file.read_text())
        assert "last_run" in state
        assert "last_result" in state
        assert "log_size_bytes" in state
