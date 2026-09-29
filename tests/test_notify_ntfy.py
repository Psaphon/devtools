"""ntfy-native notify format, tested against a real local HTTP server."""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import dtl

LOG = logging.getLogger("test.notify")


@pytest.fixture
def server():
    received: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            received.append(
                {
                    "method": self.command,
                    "headers": {k.lower(): v for k, v in self.headers.items()},
                    "body": self.rfile.read(length),
                }
            )
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{httpd.server_port}/hub-alerts"
    yield url, received
    httpd.shutdown()
    httpd.server_close()
    thread.join()


CASES = [
    (
        "feature-merged",
        {"project": "loom", "feature": "X", "pr_number": 42},
        "loom: feature X merged (#42)",
        "default",
        "white_check_mark",
    ),
    (
        "ai-failure",
        {"project": "loom", "feature": "X", "exit_code": 1, "failure_snapshot_path": None},
        "loom: AI run failed on X (exit 1)",
        "high",
        "x",
    ),
    (
        "needs-attention",
        {"project": "loom", "feature": "X", "criterion": "Review it"},
        "loom: X needs attention: Review it",
        "high",
        "warning",
    ),
    ("idle", {"timestamp": "2026-01-01T00:00:00+00:00"}, "dtl workflow idle", "low", "zzz"),
]


@pytest.mark.parametrize(("event", "payload", "body", "priority", "tags"), CASES)
def test_ntfy_format(server, event, payload, body, priority, tags):
    url, received = server
    cfg = {"url": url, "format": "ntfy", "retry_seconds": [0]}
    dtl._emit_notify_event(cfg, event, payload, LOG)
    assert len(received) == 1
    req = received[0]
    assert req["method"] == "POST"
    assert req["body"].decode("utf-8") == body
    assert req["headers"]["content-type"] == "text/plain; charset=utf-8"
    assert req["headers"]["priority"] == priority
    assert req["headers"]["tags"] == tags
    assert req["headers"]["title"] == ("dtl · loom" if "project" in payload else "dtl")
    assert len(req["headers"]["x-dtl-event-id"]) == 16


def test_ntfy_unknown_event_defaults(server):
    url, received = server
    dtl._emit_notify_event(
        {"url": url, "format": "ntfy", "retry_seconds": [0]}, "custom", {"project": "loom"}, LOG
    )
    assert received[0]["headers"]["priority"] == "default"
    assert received[0]["body"] == b"loom: custom"


def test_ntfy_events_filter_and_auth(server, tmp_path):
    url, received = server
    auth = tmp_path / "auth"
    auth.write_text("Bearer tk_x\n")
    cfg = {
        "url": url,
        "format": "ntfy",
        "events": ["idle"],
        "auth_header_file": str(auth),
        "retry_seconds": [0],
    }
    dtl._emit_notify_event(cfg, "ai-failure", {"project": "loom"}, LOG)
    assert received == []
    dtl._emit_notify_event(cfg, "idle", {}, LOG)
    assert received[0]["headers"]["authorization"] == "Bearer tk_x"


def test_json_format_unchanged(server):
    url, received = server
    payload = {"project": "loom", "feature": "X", "pr_number": 42}
    dtl._emit_notify_event({"url": url, "retry_seconds": [0]}, "feature-merged", payload, LOG)
    req = received[0]
    assert req["headers"]["content-type"] == "application/json"
    assert "title" not in req["headers"]
    body = json.loads(req["body"])
    assert body["event"] == "feature-merged"
    assert body["actions"] == []
    assert {k: body[k] for k in payload} == payload
    assert set(body) == {"event", "event_id", "timestamp", "actions", *payload}


def test_config_honours_xdg_config_home(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "xdg" / "dtl"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "notify.toml").write_text('url = "http://127.0.0.1:1/x"\nformat = "ntfy"\n')
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert dtl._load_notify_config() == {"url": "http://127.0.0.1:1/x", "format": "ntfy"}


def test_config_falls_back_to_home(tmp_path, monkeypatch):
    home_cfg = tmp_path / "home" / ".config" / "dtl"
    home_cfg.mkdir(parents=True)
    (home_cfg / "notify.toml").write_text('url = "http://127.0.0.1:1/h"\n')
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert dtl._load_notify_config() == {"url": "http://127.0.0.1:1/h"}
