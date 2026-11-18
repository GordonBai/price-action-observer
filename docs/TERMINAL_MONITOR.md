# Read-only Robinhood terminal monitor

Use the terminal to follow incoming closed bars. Use the Replay Dashboard to
inspect historical bars interactively. The monitor neither starts a dashboard
by default nor places orders or switches market-data providers.

```sh
python -m pa_lens poll-robinhood --symbols SOXL \
  --infra-root ~/robinhood-trading-infra --output tui \
  --db local_data/robinhood-v07.sqlite3 --align-close
```

Use `--count 2` for a short check, `--once` for one snapshot, or Ctrl-C to
stop continuous polling. The TUI has panels for **Market**, **Native
Indicators**, **Price Action**, and **Data Quality**. It redraws at the current
terminal size each poll, using a compact stack on narrower terminals. History
shown in the Price Action panel is labeled as not new this scan. Terminals
with insufficient visible rows can be enlarged; `--output text` gives full
details without truncation. `NO_COLOR` disables color. An explicit TUI request
on non-interactive/dumb terminals falls back to plain text. Plain text is the
default when stdout is a terminal.
Use `--output text` for readable redirected logs, or `--output jsonl` for
existing machine-readable acquisition/native records. Piped output defaults to
JSONL. `fetch-robinhood` is unchanged. Use a separate journal for a replay or
another monitor process; two writers cannot use the same journal.

Each symbol reports the latest **accepted, journaled** closed bar in UTC and its
O/H/L/C/volume, timestamp age, acquisition quality and research readiness. If a
poll has no usable new evidence, the prior bar is labeled as retained. A
successful provider call does not make a previous close fresh. This is not a
tick stream; off-session timestamps can legitimately be stale. Regular daily
timestamps are the conservative next-UTC-midnight availability boundary.

The PA context is the first-received candle-based state, not a prediction.
The first usable scan per symbol establishes a baseline; it never announces the
loaded history as new. Following scans only announce newly observed events that
pass the journal's display priority/cooldown filter and fall after that symbol's
prior close. Retained IDs are deduplicated. Stale, catch-up, fixed-end and
quarantined observations are not promoted to current announcements; the
status and any held display-eligible event count are shown. The full journal is
not filtered or rewritten. `--display-min-priority` changes editorial importance,
not confidence or win rate.

Native EMA20 and RSI14 are shown separately when their timestamps and settings
match the latest accepted bar. Warmup/source quality remain unknown and no local
fallback is used. Missing interpolation provenance is shown as
`DATA_QUALITY_UNKNOWN`; opt-in exploratory events are marked accordingly.
Quarantined revisions leave the first-received state unchanged and pause new
announcements until independently reviewed.
