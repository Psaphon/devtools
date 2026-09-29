# AI Development Prompt — notify-ntfy-native

**Branch:** `feature/notify-ntfy-native`
**Base:** `develop`

Read `CLAUDE.md`, `docs/notify.md`, and the `notify-ntfy-native` feature in `docs/DEVPLAN.md`.
Do NOT push — the host workflow handles push and PR.

## Problem
`_emit_notify_event()` POSTs a raw JSON body (`Content-Type: application/json`)
to the URL in `~/.config/dtl/notify.toml`. ntfy shows that JSON verbatim on the
phone. hub runs ntfy at `http://127.0.0.1:2586`, topic `hub-alerts` (hub cannot
resolve `*.ts.net`, so the local port is the only route).
Also, `_load_notify_config()` reads `Path.home()/.config/dtl/notify.toml` and
ignores `XDG_CONFIG_HOME`, so the test suite's config isolation doesn't cover it:
once hub has a real notify.toml, tests could push to the user's phone.

## What to build (in `dtl.py`)
1. `_load_notify_config()` reads `$XDG_CONFIG_HOME/dtl/notify.toml`, falling back
   to `~/.config/dtl/notify.toml` when `XDG_CONFIG_HOME` is unset.
2. New optional config key `format`, default `"json"` (today's behaviour,
   byte-for-byte unchanged). With `format = "ntfy"`, `_emit_notify_event()` sends:
   - body: one human-readable line built from the payload (e.g.
     `loom: feature X merged (#42)`, `loom: AI run failed on X (exit 1)`,
     `loom: X needs attention: <criterion>`, `dtl workflow idle`),
     `Content-Type: text/plain; charset=utf-8`;
   - headers `Title` (short, e.g. `dtl · loom`), `Priority`
     (`ai-failure` and `needs-attention` → `high`, `feature-merged` → `default`,
     `idle` → `low`, anything else → `default`), and `Tags` (one ntfy emoji tag
     per event type, e.g. `x`, `warning`, `white_check_mark`, `zzz`);
   - keep the existing retry/backoff, auth header, http(s)-only and
     events-filter behaviour exactly as today. Keep `event_id` in an
     `X-Dtl-Event-Id` header for deduplication.
3. `dtl notify test` goes through the configured format (it already calls the
   emit path; make sure it honours `format`).
4. `docs/notify.md`: document `format`, and add a "hub" example:
   `url = "http://127.0.0.1:2586/hub-alerts"`, `format = "ntfy"`.
5. Tests in a new `tests/test_notify_ntfy.py`, against a REAL local HTTP server
   (`http.server` on 127.0.0.1, port 0, in a thread) that records method,
   headers and body. Do NOT mock urlopen. Cover: each event type's body, Title,
   Priority and Tags in ntfy format; json format unchanged (Content-Type
   application/json, body parses as the old payload); `XDG_CONFIG_HOME` is
   honoured by `_load_notify_config()`.

## Rules
- Run `ruff check dtl.py && ruff format --check dtl.py tests/test_notify_ntfy.py` and `python -m pytest -q tests/` before committing (create a venv outside /workspace if tools are missing).
- Do NOT reformat unrelated files. Do NOT push.
- Commit message (exactly):

      feat(notify): send ntfy-native notifications

      dtl posted raw JSON, which ntfy shows verbatim on the phone. With
      format = "ntfy" in notify.toml, events become one readable line with
      Title, Priority and Tags headers; the JSON default is unchanged. The
      config now honours XDG_CONFIG_HOME so tests stay isolated from a
      real notify.toml.
