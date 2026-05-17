"""Tests for ai_run wall-clock timeout and retry-cap bail-out paths."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dtl import _resolve_provider_chain, _run_ai_with_limits


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


# ---------------------------------------------------------------------------
# _resolve_provider_chain — backward compat and chain resolution
# ---------------------------------------------------------------------------


def _write_ai_config(project_dir: Path, config: dict) -> None:
    ai_dir = project_dir / ".ai"
    ai_dir.mkdir(parents=True, exist_ok=True)
    (ai_dir / "config.json").write_text(json.dumps(config))


def test_resolve_chain_no_config_returns_claude(tmp_path):
    """No .ai/config.json at all returns ['claude']."""
    chain = _resolve_provider_chain(tmp_path)
    assert chain == ["claude"]


def test_resolve_chain_single_provider_backward_compat(tmp_path):
    """Config without provider_chain field uses config['provider']."""
    _write_ai_config(
        tmp_path,
        {"provider": "ollama", "mode": "docker", "model": None},
    )
    chain = _resolve_provider_chain(tmp_path)
    assert chain == ["ollama"]


def test_resolve_chain_explicit_provider_chain(tmp_path):
    """provider_chain list is returned as-is."""
    _write_ai_config(
        tmp_path,
        {
            "provider": "claude",
            "provider_chain": ["claude", "ollama"],
            "mode": "docker",
            "model": None,
        },
    )
    chain = _resolve_provider_chain(tmp_path)
    assert chain == ["claude", "ollama"]


def test_resolve_chain_empty_list_falls_back_to_provider(tmp_path):
    """An empty provider_chain falls back to [config['provider']]."""
    _write_ai_config(
        tmp_path,
        {
            "provider": "openclaw",
            "provider_chain": [],
            "mode": "docker",
            "model": None,
        },
    )
    chain = _resolve_provider_chain(tmp_path)
    assert chain == ["openclaw"]


def test_resolve_chain_three_providers(tmp_path):
    """Three-element chain is returned completely."""
    _write_ai_config(
        tmp_path,
        {
            "provider": "claude",
            "provider_chain": ["claude", "openclaw", "ollama"],
            "mode": "docker",
            "model": None,
        },
    )
    chain = _resolve_provider_chain(tmp_path)
    assert chain == ["claude", "openclaw", "ollama"]
