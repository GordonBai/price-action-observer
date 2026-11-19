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
terminal size every second, using a compact stack on narrower terminals. The
New York wall clock keeps moving during Robinhood requests and between polls.
Pull start, last recorded bar acquisition receipt, last completed snapshot age, and
bar close are distinct. Aging a snapshot can mark the last bar and matching
native values stale, but it never creates or recomputes observations. History
shown in the Price Action panel is labeled as not new this scan. Terminals
with insufficient visible rows can be enlarged; `--output text` gives full
details without truncation. `NO_COLOR` disables color. An explicit TUI request
on non-interactive/dumb terminals falls back to plain text. Plain text is the
default when stdout is a terminal.
Use `--output text` for readable redirected logs, or `--output jsonl` for
existing machine-readable acquisition/native records. Piped output defaults to
JSONL. `fetch-robinhood` is unchanged. Use a separate journal for a replay or
another monitor process; two writers cannot use the same journal.

Each symbol reports the latest **accepted, journaled** closed bar in New York time (EST or EDT) and its
O/H/L/C/volume, timestamp age, acquisition quality and research readiness. If a
poll has no usable new evidence, the prior bar is labeled as retained. A
successful provider call does not make a previous close fresh. This is not a
tick stream. A regular daily provider bar is timestamped at the actual XNYS
session close, typically 16:00 ET or 13:00 ET on scheduled early closes.
The daily freshness clock follows expected trading sessions with a two-hour
post-close grace period. JSONL and stored timestamps remain UTC.

The PA context is the first-received candle-based state, not a prediction.
The first usable scan per symbol establishes a baseline; it never announces the
loaded history as new. Following scans only announce newly observed events that
pass the journal's display priority/cooldown filter and fall after that symbol's
prior close. Retained IDs are deduplicated. Stale, catch-up, fixed-end and
quarantined observations are not promoted to current announcements; the
status and any held display-eligible event count are shown. The full journal is
not filtered or rewritten. `--display-min-priority` changes editorial importance,
not confidence or win rate.

The Price Action panel shows regime, 20-bar efficiency, reference ATR, active
setups and a compact reference-level strip. Event coordinates such as
Neckline, Trig, Stop, MM and Confirm are research references with
`probability=None`. The browser canvas level overlays and Phase 2 `--htf`
linkage are future work.

Native context shows EMA20, VWAP, ATR14, RSI14 and classic pivots for supported
intraday periods. Regular daily context shows EMA20, ATR14, RSI14 and MACD.
Only values that match the latest accepted bar are displayed. Warmup and source
quality remain unknown. Numeric rows are replaced by age status when stale.
Eligible bars with an omitted interpolation field show
`Interp marker: omitted by provider` in Data Quality. Use
`--strict-interpolation` to exclude omissions. Quarantined revisions preserve
the first-received state and pause current announcements.

## Structured interactive setup

Run `python -m pa_lens wizard`, or on macOS open `Start-Monitor.command` in this
checkout. The launcher uses this checkout's `.venv`, an adjacent existing infra
venv, or `python3`; `PA_OBSERVER_PYTHON` may select an existing interpreter. It
never installs packages or reads credentials. Install the normal project
requirements first and retain the already-authenticated Robinhood infra.

Choose `monitor` or `1` for live polling. This is the default. The wizard
asks for ticker(s), interval, session bounds, polling schedule, run length,
lookback, infra path and a new journal. Defaults are NVDA, 5m, regular session,
fixed 30-second wait and 10 rounds. Daily and derived 15m use regular sessions.
Daily polling starts with 180 calendar days and overlaps subsequent requests
by seven days. Derived 15m has no matching native context.

Choose `swing` or `2` for a one-shot regular daily scan. The defaults are
SPY, QQQ and NVDA, a 250-calendar-day warmup and a 25-bar focus. The wizard
asks for the infra location and uses an in-memory journal. It previews the
selected command and starts it after `yes` or `y`. For offline scans, pass
`--input` directly to `python -m pa_lens swing`.
[Daily swing options](ROBINHOOD.md#daily-swing-observations-and-local-indicators)

Each field is validated and re-prompted; there is no natural-language command
execution, trading, credential prompt or shell evaluation of typed values.
The monitor wizard uses a new journal filename. To
resume an existing compatible journal, use the direct CLI deliberately.
`q`, EOF or Ctrl-C cancels setup without a provider call. Ctrl-C stops a running
monitor. A non-TTY input/output fails immediately with a CLI alternative; use
`poll-robinhood --count N --output jsonl` for scripts and pipes.
