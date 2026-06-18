# `maid serve` — Validator Daemon

A long-lived local daemon that exposes the maid-runner validator over a Unix
socket or token-protected localhost TCP. Designed for AI agents, editor integrations, and tight TDD loops that
issue many validate calls per task. Each call avoids the Python interpreter
and import cost, which typically saves on the order of 100 ms per request.

## Quick start

```bash
# Defaults: .maid/serve.sock, .maid/serve.pid, cwd as project root
maid serve

# Custom paths
maid serve --socket /run/maid/agent.sock \
           --pidfile /run/maid/agent.pid \
           --project-root /workspace/myrepo \
           --client-timeout 30

# Windows-compatible localhost TCP transport
maid serve --transport tcp
```

Stop with `SIGTERM` or `SIGINT`. The listening socket closes, the pidfile and
socket file are removed, and in-flight client threads are joined.

## CLI options

| Flag | Default | Purpose |
|------|---------|---------|
| `--socket` | `.maid/serve.sock` | Unix socket path |
| `--pidfile` | `.maid/serve.pid` | PID file path |
| `--project-root` | `.` | Repository the daemon binds to. All `manifest_path` values are resolved under this root. |
| `--client-timeout` | `30.0` | Per-client read timeout in seconds |
| `--transport` | `unix` | Transport selector: `unix|tcp`. TCP binds `127.0.0.1`, writes `.maid/serve.port` and `.maid/serve.token`, and requires the token on every request. |

## Protocol

NDJSON over a Unix domain socket or localhost TCP. One JSON request per line,
one JSON response per line. A single connection can carry many requests in
sequence.

### Request

```json
{"id": "<correlation>", "method": "validate|ping|verify", "protocol_version": 1, "token": "<tcp-token>", "params": { ... }}
```

- `id` (string, required): echoed back in the response so clients can
  correlate.
- `method`: `validate`, `ping`, or `verify`.
- `protocol_version` (integer, optional): request protocol version. Omitted
  means version `1`. Unsupported versions return `ok: false` with
  `UNSUPPORTED_PROTOCOL_VERSION` and the request id echoed.
- `token` (string, required only for TCP): top-level token read from
  `.maid/serve.token`. Missing or invalid TCP tokens return `ok: false` with
  `BAD_TOKEN` before method dispatch.
- `params`: method-specific object (may be empty for `ping`).

### Response

Success:

```json
{"id": "...", "ok": true, "result": { ... }}
```

Request-layer failure:

```json
{"id": "...", "ok": false, "error": {"code": "...", "message": "..."}}
```

`ok` and `result.success` are deliberately separate:

- `ok: false` means the request was rejected by the protocol or handler
  layer. Codes: `MISSING_PARAM`, `BAD_MODE`, `PATH_ESCAPE`, `UNKNOWN_METHOD`,
  `UNSUPPORTED_PROTOCOL_VERSION`, `PROTOCOL_ERROR`, `HANDLER_ERROR`,
  `FRAME_TOO_LARGE`, `BAD_TOKEN`.
- `ok: true` with `result.success: false` means the validator ran and
  reported errors against the manifest.

## Methods

### `ping`

| Field | Type | Description |
|-------|------|-------------|
| Params | `{}` | None required |
| Result | `{"pid": int, "version": str, "uptime_s": float, "cache_stats": object}` | Liveness and daemon validation cache payload |

### `validate`

Mirrors `maid validate --json`. The result is `ValidationResult.to_dict()`.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `manifest_path` | `string` | (required) | Resolved under `--project-root`. Absolute paths or `..` traversals outside the root are rejected with `PATH_ESCAPE`. |
| `mode` | `"schema"\|"behavioral"\|"implementation"` | `"implementation"` | Validation mode |
| `manifest_dir` | `string` | `"manifests/"` | Manifest directory for chain merging |
| `no_chain` | `bool` | `false` | Disable chain merging |
| `check_assertions` | `bool` | `false` | Behavioral assertion checks |
| `check_stubs` | `bool` | `false` | Implementation stub checks |
| `fail_on_warnings` | `bool` | `false` | Treat warnings as errors |

Any client-supplied `project_root` in `params` is ignored. The daemon
validates only inside the project root it was started with.

### `verify`

Runs the daemon-supported subset of `maid verify --json`. The daemon executes
the validation, coherence, and file-tracking stages inside the startup
`--project-root`, mirrors verify defaults for warning strictness and fail-fast
behavior, and reports the subprocess `tests` stage as skipped instead of
running test commands in the daemon process.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `manifest_dir` | `string` | `"manifests/"` | Manifest directory resolved under `--project-root`. Absolute paths or `..` traversals outside the root are rejected with `PATH_ESCAPE`. |
| `allow_empty` | `bool` | `false` | Match `maid verify --allow-empty`; when no active manifests exist, daemon-supported stages after validation are reported as skipped. |
| `check_assertions` | `bool` | `true` | Behavioral assertion checks |
| `check_stubs` | `bool` | `true` | Implementation stub checks |
| `fail_fast` | `bool` | `true` | Stop after the first failing daemon-supported stage |
| `fail_on_warnings` | `bool` | `true` | Treat blocking warnings as verify failures |

Any client-supplied `project_root` in `params` is ignored. The response uses
the same JSON shape as `maid verify --json` for the stages the daemon runs.

## Security defaults

- Runtime directory created with mode `0700`; existing directories with
  group/world bits are refused with a clear error message.
- Socket file `chmod` to `0600` immediately after `bind()`, with `umask
  0o077` set during bind to close the race window.
- TCP transport binds only `127.0.0.1`. The daemon writes `.maid/serve.port`
  and `.maid/serve.token` under the runtime directory; both files are owner
  only, and every TCP request must carry the token before any handler runs.
- Pidfile claimed atomically via `O_CREAT | O_EXCL`. Stale pidfiles whose
  PID is no longer running are removed and replaced; live PIDs cause startup
  to exit non-zero with a clear error.
- Existing entries at the socket path are only unlinked when they are
  actually Unix sockets (`S_ISSOCK`). Regular files, directories, and FIFOs
  are preserved and startup fails with a clear message.
- `check_stale_pidfile()` touches the pidfile only. Socket cleanup is the
  caller's responsibility and goes through the `S_ISSOCK` guard, so custom
  socket/pidfile basenames cannot delete an unrelated process's socket.

## Robustness defaults

- Thread-per-client accept loop. One slow or idle connection cannot block
  the daemon.
- 1 MiB cap on a single NDJSON request frame. A client that keeps sending
  bytes without a terminating newline receives a `FRAME_TOO_LARGE` error and
  is closed; the daemon keeps serving.
- Malformed JSON returns a `PROTOCOL_ERROR` response and the connection
  stays open for subsequent requests.
- Per-client socket read timeout (configurable via `--client-timeout`).
  Timeouts close the offending client only.

## Library entry points

```python
from maid_runner.daemon import (
    Server,
    serve,
    Request,
    Response,
    ProtocolError,
    DaemonRequestError,
)
from maid_runner.daemon.client import (
    DaemonClient,
    DaemonClientError,
    resolve_daemon_endpoint,
)
```

- `serve(socket_path, pidfile_path, client_timeout_s, project_root=".",
  transport="unix")` is the top-level entry point. Returns a process exit code.
- `Server` is the underlying class if you need to embed the daemon in another
  process.
- `resolve_daemon_endpoint(runtime_dir=".maid", socket_path=".maid/serve.sock",
  transport="auto")` discovers the local Unix socket or token-protected TCP
  runtime files.
- `DaemonClient(endpoint).ping()`, `.validate(...)`, and `.verify(...)` are the
  public long-lived client API for agents and editor integrations.
- `DaemonClientError(code, message)` reports transport failures and daemon
  `ok: false` responses without falling back to direct validation.
- `DaemonRequestError(code, message)` is the contract handlers use to
  signal request-layer failures. The dispatcher converts it to an `ok: false`
  response.

## Long-Lived Client

```python
from maid_runner.daemon.client import DaemonClient, resolve_daemon_endpoint


endpoint = resolve_daemon_endpoint(transport="auto")
client = DaemonClient(endpoint)

print(client.ping())
print(client.validate("manifests/add-auth.manifest.yaml", mode="behavioral"))
print(client.verify("manifests/", allow_empty=False))
```

`maid daemon ping|validate|verify` exposes the same client as a diagnostic CLI
for humans and scripts checking a running daemon. It still starts a fresh CLI
process for each call, so it is not the performance path that long-lived agents
and editor integrations should use.

## When to use it

- AI coding agents and editor integrations that issue many validate calls in
  a session.
- CI helpers that batch many per-manifest validations on the same checkout.
- Local TDD loops where startup latency dominates per-call wall time.

For one-shot validation or CI fan-out across separate checkouts, the plain
`maid validate` CLI is simpler and avoids the daemon lifecycle.
`maid test` remains a subprocess command runner; use the daemon for the
in-process validation and verify subset during edit loops, then run full
`maid test` and strict `maid verify` before handoff.
