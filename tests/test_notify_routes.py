"""Watchdog anomalies and failed AI runs must reach notify.toml (ntfy on hub).

Both used to go only through .ai/notify.py, which speaks Telegram only, so on
hub they were silent (2026-09-29).
"""

import logging
from pathlib import Path

import pytest

import dtl


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(dtl, "_load_notify_config", lambda: {"url": "http://127.0.0.1:9/x"})
    monkeypatch.setattr(
        dtl,
        "_emit_notify_event",
        lambda cfg, event_type, payload, log: events.append((event_type, payload)),
    )
    return events


def test_watchdog_anomalies_go_to_notify_config(tmp_path: Path, sent: list) -> None:
    project = tmp_path / "loom"
    project.mkdir()
    dtl._watchdog_notify_project(project, ["stalled 3h", "dirty tree"], logging.getLogger("t"))
    assert sent == [
        (
            "needs-attention",
            {"project": "loom", "feature": "watchdog", "criterion": "stalled 3h; dirty tree"},
        )
    ]


def test_no_anomalies_sends_nothing(tmp_path: Path, sent: list) -> None:
    dtl._watchdog_notify_project(tmp_path, [], logging.getLogger("t"))
    assert sent == []


def test_failed_ai_run_goes_to_notify_config(tmp_path: Path, sent: list) -> None:
    ai_dir = tmp_path / "loom" / ".ai"
    ai_dir.mkdir(parents=True)
    dtl._send_notification(ai_dir, 42, "boom")
    assert sent == [("ai-failure", {"project": "loom", "feature": "dtl ai run", "exit_code": 42})]


def test_successful_ai_run_sends_no_ntfy_event(tmp_path: Path, sent: list) -> None:
    ai_dir = tmp_path / "loom" / ".ai"
    ai_dir.mkdir(parents=True)
    dtl._send_notification(ai_dir, 0, "ok")
    assert sent == []


def test_no_config_sends_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dtl, "_load_notify_config", lambda: None)
    called = []
    monkeypatch.setattr(dtl, "_emit_notify_event", lambda *a: called.append(a))
    dtl._send_notification(tmp_path / ".ai", 1, "x")
    dtl._watchdog_notify_project(tmp_path, ["a"], logging.getLogger("t"))
    assert called == []


def test_watchdog_skips_notify_py_when_config_exists(
    tmp_path: Path, sent: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "loom"
    (project / ".ai").mkdir(parents=True)
    (project / ".ai" / "notify.py").write_text("raise SystemExit(1)\n")
    ran = []
    monkeypatch.setattr(dtl.subprocess, "run", lambda *a, **k: ran.append(a))
    dtl._watchdog_notify_project(project, ["x"], logging.getLogger("t"))
    assert len(sent) == 1 and ran == []
