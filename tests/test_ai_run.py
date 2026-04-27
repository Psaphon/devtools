"""Tests for ai_run wall-clock timeout and retry-cap bail-out paths."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dtl import _run_ai_with_limits, _write_failure_report


# ---------------------------------------------------------------------------
# _write_failure_report
# ---------------------------------------------------------------------------


def test_write_failure_report_creates_file(tmp_path):
    lines = ["line one\n", "line two\n"]
    _write_failure_report(tmp_path, "my-feature", "wall_clock", lines)
    report = tmp_path / "FAILURE-REPORT.md"
    assert report.exists()
    text = report.read_text()
    assert "Wall-clock timeout exceeded" in text
    assert "my-feature" in text
    assert "line one" in text
    assert "line two" in text


def test_write_failure_report_truncates_to_200_lines(tmp_path):
    lines = [f"line {i}\n" for i in range(300)]
    _write_failure_report(tmp_path, "feat", "retry_cap", lines)
    text = (tmp_path / "FAILURE-REPORT.md").read_text()
    # last line is 299, first of last 200 is 100
    assert "line 299" in text
    assert "line 99\n" not in text


def test_write_failure_report_unknown_feature(tmp_path):
    _write_failure_report(tmp_path, "", "wall_clock", [])
    text = (tmp_path / "FAILURE-REPORT.md").read_text()
    assert "(unknown)" in text


def test_write_failure_report_retry_cap_label(tmp_path):
    _write_failure_report(tmp_path, "feat", "retry_cap", [])
    text = (tmp_path / "FAILURE-REPORT.md").read_text()
    assert "AI retry cap exceeded" in text


# ---------------------------------------------------------------------------
# _run_ai_with_limits — wall-clock timeout
# ---------------------------------------------------------------------------


def test_run_ai_with_limits_wall_clock_timeout(tmp_path):
    """A subprocess that sleeps longer than the limit should be killed (code 124)."""
    cmd = [sys.executable, "-c", "import time; time.sleep(60)"]
    start = time.monotonic()
    code, lines = _run_ai_with_limits(
        cmd,
        {},
        max_wall_clock=2,
        max_ai_retries=0,  # disabled
    )
    elapsed = time.monotonic() - start
    assert code == 124
    assert elapsed < 10  # killed well before natural end


def test_run_ai_with_limits_wall_clock_exit_code_124(tmp_path):
    cmd = [sys.executable, "-c", "import time; time.sleep(60)"]
    code, _ = _run_ai_with_limits(cmd, {}, max_wall_clock=1, max_ai_retries=0)
    assert code == 124


# ---------------------------------------------------------------------------
# _run_ai_with_limits — retry cap
# ---------------------------------------------------------------------------


def test_run_ai_with_limits_retry_cap(tmp_path):
    """A subprocess that emits retry markers should be killed after N occurrences."""
    # Emit 5 "tests failed" lines then sleep; cap is 3
    script = (
        "import sys, time\n"
        "for _ in range(5):\n"
        "    print('tests failed, retrying...', flush=True)\n"
        "    time.sleep(0.1)\n"
        "time.sleep(60)\n"
    )
    cmd = [sys.executable, "-c", script]
    code, lines = _run_ai_with_limits(
        cmd,
        {},
        max_wall_clock=30,
        max_ai_retries=3,
    )
    assert code == 125
    # Should have captured at least 3 retry lines before killing
    retry_lines = [line for line in lines if "tests failed" in line]
    assert len(retry_lines) >= 3


def test_run_ai_with_limits_retry_cap_exit_code_125(tmp_path):
    script = (
        "import sys, time\n"
        "for _ in range(4):\n"
        "    print('retrying', flush=True)\n"
        "    time.sleep(0.05)\n"
        "time.sleep(60)\n"
    )
    cmd = [sys.executable, "-c", script]
    code, _ = _run_ai_with_limits(cmd, {}, max_wall_clock=30, max_ai_retries=3)
    assert code == 125


def test_run_ai_with_limits_retry_disabled_does_not_kill(tmp_path):
    """When max_ai_retries=0, retry markers should not trigger a kill."""
    script = (
        "import sys\n"
        "for _ in range(5):\n"
        "    print('tests failed, retrying...', flush=True)\n"
        "print('done')\n"
    )
    cmd = [sys.executable, "-c", script]
    code, lines = _run_ai_with_limits(
        cmd,
        {},
        max_wall_clock=30,
        max_ai_retries=0,
    )
    assert code == 0  # process exits naturally


# ---------------------------------------------------------------------------
# _run_ai_with_limits — successful run
# ---------------------------------------------------------------------------


def test_run_ai_with_limits_success(tmp_path):
    """A subprocess that exits 0 with no triggers should return (0, lines)."""
    script = "print('hello world')\n"
    cmd = [sys.executable, "-c", script]
    code, lines = _run_ai_with_limits(cmd, {}, max_wall_clock=30, max_ai_retries=3)
    assert code == 0
    assert any("hello world" in line for line in lines)


def test_run_ai_with_limits_captures_output(tmp_path):
    script = "for i in range(3): print(f'line {i}')\n"
    cmd = [sys.executable, "-c", script]
    code, lines = _run_ai_with_limits(cmd, {}, max_wall_clock=30, max_ai_retries=0)
    assert code == 0
    assert len(lines) == 3
    assert "line 0\n" in lines


def test_run_ai_with_limits_nonzero_exit_passthrough(tmp_path):
    cmd = [sys.executable, "-c", "import sys; sys.exit(42)"]
    code, _ = _run_ai_with_limits(cmd, {}, max_wall_clock=30, max_ai_retries=0)
    assert code == 42
