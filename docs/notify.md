# dtl Notification Hook

`dtl workflow run` can POST structured events to an HTTP endpoint whenever
significant workflow state changes occur. The primary use case is forwarding
events to [ntfy](https://ntfy.sh) on a hub machine, which then forwards them
to iOS via APNs and surfaces action buttons on a watch.

## Config file

Create `~/.config/dtl/notify.toml` (gitignored, optional — absent means no
notifications, log-only):

```toml
# Required: the endpoint that receives JSON POSTs.
url = "https://ntfy.<tailnet>.ts.net/dtl"

# Which event types to deliver. Omit or set to [] to deliver all.
events = ["ai-failure", "feature-merged", "needs-attention", "idle"]

# Optional: path to a file whose contents become the Authorization header.
# Works for Bearer, Basic, or any other scheme — the file contents are used verbatim.
# auth_header_file = "/etc/dtl/ntfy-auth"

# Retry backoff in seconds. Delivery is attempted len(retry_seconds) times total,
# then abandoned. Failed deliveries are logged but never block the workflow.
retry_seconds = [1, 5, 30]
```

Config is read once at the start of each `dtl workflow run` invocation.

## Events

All POSTs are JSON with `Content-Type: application/json`. Every event body
includes these top-level fields:

| Field | Type | Description |
|-------|------|-------------|
| `event` | string | Event type (see below) |
| `event_id` | string | 16-char hex digest, stable across retries (use for deduplication) |
| `timestamp` | string | ISO 8601 UTC timestamp of emission |
| `actions` | array | ntfy action button objects `{label, url}` (may be empty) |

### `ai-failure`

Emitted when the AI subprocess exits with a non-zero exit code.

```json
{
  "event": "ai-failure",
  "event_id": "a1b2c3d4e5f60718",
  "timestamp": "2026-05-13T02:34:56.789012+00:00",
  "actions": [],
  "project": "myproject",
  "feature": "beta-feature",
  "exit_code": 1,
  "failure_snapshot_path": "/home/user/.local/state/dtl/myproject-beta-feature-failure-20260513T023456Z.md"
}
```

`failure_snapshot_path` is the full path to the AI failure snapshot written by
the `ai-failure-snapshot` feature. It is `null` when snapshot writing itself
failed.

### `feature-merged`

Emitted after `dtl workflow run` detects that a PR has been merged (via
`gh pr view --json state`).

```json
{
  "event": "feature-merged",
  "event_id": "b2c3d4e5f6071829",
  "timestamp": "2026-05-13T03:10:00.000000+00:00",
  "actions": [],
  "project": "myproject",
  "feature": "beta-feature",
  "pr_number": 9
}
```

`pr_number` is extracted from the PR URL. It is `null` if the URL did not
contain a numeric PR identifier.

### `needs-attention`

Emitted for each acceptance criterion in the feature block that contains the
`[HUMAN]` tag. This signals that human review is required before the PR can
be considered complete.

```json
{
  "event": "needs-attention",
  "event_id": "c3d4e5f607182930",
  "timestamp": "2026-05-13T02:35:10.000000+00:00",
  "actions": [],
  "project": "myproject",
  "feature": "beta-feature",
  "criterion": "- [ ] [HUMAN] Approve the deployment config"
}
```

To mark a criterion as requiring human review, add `[HUMAN]` anywhere in the
checkbox line in `DEVPLAN.md`:

```markdown
### Acceptance Criteria

- [ ] All tests pass
- [ ] [HUMAN] Review the generated docker-compose.yml before merging
```

### `idle`

Emitted when `dtl workflow run` has no more Not-Started features to work on
across all configured projects and exits the loop.

```json
{
  "event": "idle",
  "event_id": "d4e5f60718293041",
  "timestamp": "2026-05-13T06:00:00.000000+00:00",
  "actions": [],
  "timestamp": "2026-05-13T06:00:00.000000+00:00"
}
```

## Testing the config

Send a synthetic event without running a full workflow:

```bash
# Send an idle event (default)
dtl notify test

# Send a specific event type
dtl notify test --event ai-failure
dtl notify test --event feature-merged
dtl notify test --event needs-attention
```

Exit code is 1 if `~/.config/dtl/notify.toml` is absent.

## Authentication

The `auth_header_file` option points to a file whose **entire contents** (after
stripping leading/trailing whitespace) become the `Authorization` HTTP header
value. Examples:

```
# Bearer token
Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# ntfy username:password (Basic)
Basic dXNlcjpwYXNz

# ntfy access token
Bearer tk_...
```

Keep this file outside the project directory (e.g. `/etc/dtl/ntfy-auth` or
`~/.config/dtl/ntfy-auth`) and set permissions to `600`.

## ntfy action-handler integration

The `actions` array in each event body is intended for
[ntfy action buttons](https://docs.ntfy.sh/publish/#action-buttons). When you
run a companion `action-handlers` service on the hub, you can populate action
URLs pointing to that service.

The hub's action-handler endpoint accepts POST requests and dispatches them
(e.g. triggering a manual `gh pr merge`). The URL scheme is:

```
POST https://<hub>/api/<verb>/<project>/<pr_number>
```

Currently `actions` is always an empty array. To add action buttons, extend
`_emit_notify_event` in `dtl.py` to read an optional `action_handler_url`
from the config and construct button URLs per event type.

## Delivery guarantees

- Delivery is attempted up to `len(retry_seconds)` times with the specified
  backoff between attempts.
- Total delivery time is bounded by `sum(retry_seconds) + len(retry_seconds) * 10`
  seconds (10 s per attempt timeout).
- Failed deliveries are logged at `INFO` level and never raise an exception.
- The workflow never blocks or exits due to a notification failure.
- The `event_id` field is a deterministic hash of the event type and payload,
  so retries will produce the same `event_id`. Use it for deduplication on the
  hub side.
