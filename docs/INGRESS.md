# Closed-bar ingress and local readiness

This is a research receiver, not a market-data subscription or a public deployment.
The application binds to `127.0.0.1` by default. It does not place orders.

## Standard API

`make_server(journal, token, host='127.0.0.1', port=8080)` requires a nonempty API
secret supplied by the operator. `POST /bar`, `POST /webhook`, `GET /snapshot`
and `GET /health` require `Authorization: Bearer <API secret>`.
Query-string credentials do **not** authenticate these routes.

- `/bar`: normalized bar object, `time` = timezone-aware **close** timestamp.
- `/webhook`: `ai-agent-lens/v1` JSON, with OHLCV inside `candle`.
- The unauthenticated `/` route serves only a static dashboard shell; data access
  requires the token entered in the page, held in memory rather than storage.

## Optional native TradingView-compatible receiver route

TradingView alerts cannot normally attach a custom Bearer header. To receive
those alerts, an operator may explicitly opt in with a **distinct** secret:

```python
import os
from pa_lens.service import Journal, make_server

journal = Journal('local-bars.sqlite')
server = make_server(
    journal,
    token=os.environ['PA_LENS_TOKEN'],
    tv_token=os.environ['PA_LENS_TV_TOKEN'],  # opt-in; omitted/None disables route
)
server.serve_forever()
```

The receiver accepts `POST /tradingview?token=<separate secret>` carrying the
original `ai-agent-lens/v1` JSON. This is a compatible receiver or relay endpoint,
**not a claim that an internet-accessible URL exists or that live packets were
received**. An empty token is rejected; omit it to disable. API and TradingView
secrets must differ. The TradingView secret cannot read snapshots or authenticate
`/bar`. Duplicate token query parameters are rejected. Token comparisons are
constant-time; application request logging is disabled and responses do not echo
secrets. There is no runtime token-creation or account-configuration workflow.

Before exposing this endpoint:
1. Use a separately reviewed TLS reverse proxy with a valid HTTPS hostname. Do
   not expose the Python development-style HTTP server directly to the internet.
2. Disable or redact query strings in proxy/access/error logs, tracing, analytics
   and monitoring. A URL credential can leak through logs, copied URLs or browser
   history; it must be treated as a secret, not a shareable dashboard link.
3. Add an ingress IP allowlist if the sender's currently documented addresses
   can be verified; do not invent or permanently assume provider IP ranges.
4. Configure request/rate/time/concurrency limits at the reverse proxy and
   protect the dashboard/data API separately. This receiver is not a hardened
   multi-tenant server. Rotate the separate secret if leaked.
5. Verify entitlement, alert configuration and actual current completed-bar
   delivery independently. No paid plan, proxy, DNS or cloud hosting is configured
   by this project.

## Validation and bounded state

Both ingress modes enforce JSON objects, a 64 KiB body bound, completed-bar flags
(`final` and `bar_closed` cannot be false), valid OHLCV and aware close timestamps.
Close times more than 5 seconds in the future are rejected. Exact duplicates are
idempotent; revisions and out-of-order records are rejected rather than rewriting
past decisions. Source, symbol and timeframe form a stream; one journal accepts
at most 64 distinct streams. Late/revised data requires a separate research replay.
No reconstructed or synthetic missing bars are inserted.

## Replay identity and upgrading

SQLite metadata pins the configuration hash, `ENGINE_VERSION`, and SHA-256 of the
`core.py` plus `advanced.py` rule sources (when present). Startup refuses mismatches
or legacy populated journals with missing identity. This intentionally treats even
source-only rule edits conservatively. Use a **new database** for a new ruleset or
an explicit independently verified migration; never delete metadata to suppress
the guard. Back up the old journal to preserve the evidence trail. A docs-only
commit does not change the source fingerprint. Restart the service after source
changes; hot-reloading code is unsupported.

## What readiness means

`/snapshot` and `/health` expose:
- `ready: false`, `readiness: WAITING_FOR_DATA` when no streams exist.
- Per-stream `WARMUP` when current-segment history is below the engine minimum.
- Per-stream `STALE` / `FUTURE` when submitted timestamps are too old / ahead.
- `READY_FOR_RESEARCH` only when every stream is recent and warmed up; otherwise
  aggregate `NOT_READY`.

Freshness uses a threshold of `max(120 seconds, 2 × interval)`; closed markets can
therefore show STALE without implying a collection outage. The age is measured
from the submitted **bar close**, not from server receipt. `ready` indicates only
local research-processing prerequisites. `live_verified` remains **false**:
recent timestamps alone do not prove an authentic real-time feed, reliable
hosting, market completeness, a profitable strategy, or permission to trade.

## One owner per journal

On Linux/macOS, `Journal` holds a nonblocking exclusive `fcntl.flock` on the
actual database file for the full instance lifetime. A second instance or process
opening that database fails immediately with `journal already in use`, preventing
independent in-memory engines from silently missing each other's bars. The lock
is released on `close()`, construction failure, or process exit; close is
idempotent. Symlink paths resolve to the same database. Do not rename/replace an
active database or manually bypass the service with external writers. Use local
filesystems with working advisory locks; network-filesystem semantics are not
validated. `:memory:` journals are independent and do not take a file lock.
