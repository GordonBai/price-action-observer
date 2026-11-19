"""Human projection of current read-only polling, not another signal engine."""
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import os
import re
import shutil
import threading
import unicodedata
from zoneinfo import ZoneInfo

from .context_summary import _setup_levels
from .core import parse_time
from .timeframes import is_daily_fresh

_SEEN_LIMIT = 4096
_NEW_YORK = ZoneInfo("America/New_York")


def _ny(value):
    return parse_time(value).astimezone(_NEW_YORK).strftime("%Y-%m-%d %H:%M:%S %Z")


def _period(value):
    return value + "m" if value.isdigit() else value


_AVAILABLE = "AVAILABLE_SOURCE_UNKNOWN"
_NATIVE_LABELS = (("ema20", "EMA20"), ("vwap", "VWAP"), ("atr14", "ATR14"),
                  ("rsi14", "RSI14"), ("pivot_points", "Pivot"), ("macd", "MACD"))
_LEVEL_LABELS = (("neckline", "Neckline"), ("trigger", "Trig"), ("stop", "Stop"),
                 ("target", "MM"), ("confirmation_level", "Confirm"))


def _native_value(key, row):
    values = row.get("values", {})
    if key == "pivot_points":
        return f"P {values['pivot']} / R1 {values['r1']} / S1 {values['s1']}"
    if key == "macd":
        delta = row.get("histogram_delta")
        value = f"{values['macd']} / Sig {values['signal']} / Hist {values['histogram']}"
        return value if delta is None else f"{value} / Delta {delta}"
    value = str(row["value"])
    if row.get("relation"):
        value += f" | close {row['relation']}"
    if key == "ema20" and row.get("distance") is not None:
        value += f" {float(row['distance']):+.8g}"
        if row.get("atr_multiple") is not None:
            value += f" ({float(row['atr_multiple']):+.2f} ATR)"
    return value


def _native_rows(context):
    rows = []
    for key, label in _NATIVE_LABELS:
        if key not in context:
            continue
        entry = context[key]
        if entry.get("status") == _AVAILABLE:
            rows.append((label, _native_value(key, entry), entry["effective_at"], None))
        else:
            rows.append((label, entry.get("status", "UNAVAILABLE"), None, entry.get("reason")))
    return rows


def _native_lines(context, *, daily=False):
    status = context.get("status", "UNAVAILABLE")
    if status == "NOT_REQUESTED":
        return ["  Native context: NOT REQUESTED"]
    lines = [f"  Native context: {status} (warmup/source quality unknown)"]
    if context.get("reason"):
        lines.append(f"    {context['reason']}")
    for label, value, timestamp, reason in _native_rows(context):
        if timestamp:
            timing = "available at" if daily else "effective"
            lines.append(f"    {label} {value} | {timing} {_ny(timestamp)}")
        else:
            lines.append(f"    {label}: {value}" + (f" | {reason}" if reason else ""))
    return lines


def _level_text(levels):
    return " · ".join(f"{label} {levels[key]:.8g}" for key, label in _LEVEL_LABELS if key in levels)


def _bar_freshness(close, now, limit, daily):
    age = (now - close).total_seconds()
    if age < -5:
        return "FUTURE"
    if daily:
        try:
            return "RECENT" if is_daily_fresh(close, now) else "STALE"
        except ValueError:
            # Match the journal fallback for legacy non-session daily inputs.
            pass
    return "STALE" if age > limit else "RECENT"


class TerminalMonitor:
    """Keep a per-session baseline plus a bounded set of presented event IDs."""

    def __init__(self, symbols):
        self.symbols = tuple(symbols)
        self.last_close = {}
        self.seen = set()
        self.seen_order = deque()
        self.round = 0

    def _record_id(self, event_id):
        if event_id in self.seen:
            return False
        self.seen.add(event_id)
        self.seen_order.append(event_id)
        if len(self.seen_order) > _SEEN_LIMIT:
            self.seen.remove(self.seen_order.popleft())
        return True

    def render(self, snapshot, receipts, *, now, source, fixed_end=False, native_enabled=True):
        """Render a human-readable text snapshot."""
        return self.view(snapshot, receipts, now=now, source=source, fixed_end=fixed_end,
                         native_enabled=native_enabled)["text"]

    def view(self, snapshot, receipts, *, now, source, fixed_end=False, native_enabled=True):
        """Project detached journal state once for either layout."""
        self.round += 1
        line = (f"[{_ny(now)}] Robinhood read-only monitor | poll {self.round} | "
                f"{source} | research only")
        lines = [line + (" | FIXED END (not following live)" if fixed_end else "")]
        panels = {key: [] for key in ("MARKET", "NATIVE INDICATORS", "PRICE ACTION", "DATA QUALITY")}
        streams = {s["symbol"]: s for s in snapshot["streams"] if s["source"] == source}
        acquisitions = {s: (r, len(symbols)) for symbols, r in receipts for s in symbols}
        transport_errors = {entry["symbol"] for entry in snapshot.get("transport", ())
                            if entry["source"] == source and entry.get("status") == "error"}
        risk = dict.fromkeys(("QUARANTINE", "ERROR", "UNKNOWN", "STALE"), 0)
        receipt_ids = {result.get("acquisition_id") for _, result in receipts} - {None}
        recorded_receipts = [parse_time(item["received_at"]) for item in snapshot.get("acquisitions", ())
                             if item["id"] in receipt_ids and item["source"] == source]
        clock_slots = []
        for symbol in self.symbols:
            stream = streams.get(symbol)
            result, batch_size = acquisitions.get(symbol, ({}, 0))
            acquisition = result.get("status", "NO_RECEIPT")
            if symbol in result.get("quality", {}).get("no_usable_symbols", []):
                acquisition = "NO_USABLE_BARS"
            omitted_by_symbol = result.get("omitted_emitted_by_symbol")
            omitted = (omitted_by_symbol.get(symbol, 0) if omitted_by_symbol is not None
                       else result.get("quality", {}).get("omitted_emitted", 0) if batch_size == 1 else 0)
            stream_quality = stream.get("data_quality", {}) if stream else {}
            stream_flags = {stream_quality.get("status"), stream_quality.get("acquisition_status"),
                            stream.get("readiness") if stream else None, acquisition}
            risk["QUARANTINE"] += int(bool(stream_quality.get("quarantined_count"))
                                      or "DATA_REVIEW_REQUIRED" in stream_flags)
            risk["ERROR"] += int(symbol in transport_errors
                                 or any(flag and "ERROR" in flag for flag in stream_flags))
            risk["UNKNOWN"] += int(source.endswith(":accept_unknown")
                                   or "DATA_QUALITY_UNKNOWN" in stream_flags)
            risk["STALE"] += int(bool(stream) and stream.get("freshness") in ("STALE", "FUTURE"))
            ingested, repeats = result.get("ingested"), result.get("duplicates")
            summary = f" | batch accepted={ingested}, unchanged={repeats}" if isinstance(ingested, int) else ""
            lines.append(f"{symbol} | acquisition={acquisition}{summary}")
            if not stream or not stream["bars"]:
                lines.append("  No accepted closed bar. No new key PA event.")
                panels["MARKET"].append(f"{symbol}  No accepted closed bar")
                panels["NATIVE INDICATORS"].append(f"{symbol}  No bar to match")
                panels["PRICE ACTION"].append(f"{symbol}  No new key PA event")
                panels["DATA QUALITY"].extend((symbol, f"Acquisition: {acquisition}"))
                continue
            last = stream["bars"][-1]
            close = parse_time(last["time"])
            previous = self.last_close.get(symbol)
            if previous is None or close > previous:
                self.last_close[symbol] = close
            quality = stream["data_quality"]
            freshness = stream["freshness"]
            counts = quality.get("quarantined_count", 0)
            flags = [value for value in (quality.get("status"), quality.get("acquisition_status"))
                     if value and value != "NO_QUARANTINED_OBSERVATIONS"]
            if source.endswith(":accept_unknown") and "DATA_QUALITY_UNKNOWN" not in flags:
                flags.append("DATA_QUALITY_UNKNOWN")
            daily = stream["timeframe"] == "D"
            bar_label = "daily bar available at" if daily else f"{_period(stream['timeframe'])} closed bar"
            market_label = "Daily bar available at" if daily else f"{_period(stream['timeframe'])} CLOSED"
            lines.append(f"  Latest journaled {bar_label} {_ny(close)} "
                         f"| O={last['open']} H={last['high']} L={last['low']} C={last['close']} V={last['volume']}")
            status = f"  {freshness} | age={stream['age_seconds']:.0f}s | {stream['readiness']}"
            market_row = len(panels["MARKET"]) + 1
            panels["MARKET"].extend((f"{symbol}  {market_label}",
                                     f"{_ny(close)}  |  {freshness}",
                                     f"O {last['open']}   H {last['high']}",
                                     f"L {last['low']}   C {last['close']}   V {last['volume']}"))
            if flags:
                status += " | " + " / ".join(dict.fromkeys(flags))
            lines.append(status)
            quality_row = len(panels["DATA QUALITY"])
            panels["DATA QUALITY"].extend((f"{symbol}  {freshness} | age {stream['age_seconds']:.0f}s",
                                           *dict.fromkeys(flags or [acquisition])))
            if flags and acquisition not in flags:
                panels["DATA QUALITY"].append(f"Acquisition: {acquisition}")
            readiness_row = None
            if stream["readiness"] not in (*flags, freshness, acquisition):
                if stream["readiness"] in ("READY_FOR_RESEARCH", "WARMUP"):
                    readiness_row = len(panels["DATA QUALITY"])
                panels["DATA QUALITY"].append(stream["readiness"])
            if counts:
                lines.append(f"  QUARANTINE: {counts} known revision/late arrival record(s); "
                             "first-received OHLC retained, PA judgments not refreshed.")
                panels["DATA QUALITY"].insert(len(panels["DATA QUALITY"]) - 1,
                                              f"QUARANTINE: {counts} revision/late rows")
            if ingested == 0 and isinstance(repeats, int):
                panels["MARKET"].append("No newly accepted bar this poll")
            if acquisition in ("NO_RECEIPT", "NO_USABLE_BARS"):
                lines.append("  Latest bar is retained from the journal, not confirmed by this poll.")
                panels["MARKET"].append("Retained from journal, not this poll")
            if omitted:
                lines.append("  Interp marker: omitted by provider")
                panels["DATA QUALITY"].append("Interp marker: omitted by provider")
            summary = stream.get("summary", {})
            regime = summary.get("regime", {})
            context = regime.get("context", stream["state"].get("context", "unavailable"))
            efficiency = regime.get("efficiency_20")
            efficiency_text = f"20B eff {efficiency:.2f}" if efficiency is not None else ""
            native_atr = regime.get("atr_origin") == "robinhood_native_atr14"
            engine_atr = regime.get("engine_atr") if native_atr else regime.get("reference_atr")
            local = f"Engine ATR15 {engine_atr:.8g}" if engine_atr is not None else ""
            atr = regime.get("reference_atr")
            use_native_atr = native_enabled and native_atr and atr is not None
            reference = f"Native ATR14 {atr:.8g}" if use_native_atr else local
            context_detail = " | ".join(filter(None, (efficiency_text, reference)))
            stale_detail = " | ".join(filter(None, (efficiency_text, local)))
            detail = f" | {context_detail}" if context_detail else ""
            lines.append(f"  PA context: {context}{detail} (first-received bars; research only)")
            pa = panels["PRICE ACTION"]
            pa.append(f"{symbol}  {context}")
            native = stream.get("native_interpretation", {})
            native_rows = []
            effective_at = []
            native_header = None
            if native_enabled:
                lines.extend(_native_lines(native, daily=daily))
                panels["NATIVE INDICATORS"].append(f"{symbol}  {native.get('status', 'UNAVAILABLE')}")
                native_header = len(panels["NATIVE INDICATORS"]) - 1
                rows = _native_rows({"ema20": {}, "rsi14": {}, **native})
                for index, (label, value, timestamp, _) in enumerate(rows):
                    panel = panels["NATIVE INDICATORS"]
                    if (label == "RSI14" and timestamp and index and rows[index - 1][0] == "ATR14"
                            and rows[index - 1][2] == timestamp):
                        panel[-1] += f" / {label} {value}"
                        native_rows[-1] = (len(panel) - 1, "ATR14 / RSI14")
                    else:
                        if timestamp:
                            native_rows.append((len(panel), label))
                        panel.append(f"{label} {value}" if timestamp else f"{label}  {value}")
                    if timestamp:
                        effective_at.append(timestamp)
                for timestamp in dict.fromkeys(effective_at):
                    if daily:
                        panels["NATIVE INDICATORS"].extend(("Available at:", _ny(timestamp)))
                    else:
                        panels["NATIVE INDICATORS"].append(f"Effective {_ny(timestamp)}")
                panels["NATIVE INDICATORS"].append("Warmup / source quality unknown")
                reasons = list(dict.fromkeys(r for r in (
                    native.get("reason"), *(row[3] for row in rows)) if r))
                panels["NATIVE INDICATORS"].extend(reasons[:2])
            else:
                lines.append("  Native context: NOT REQUESTED; no local fallback.")
                panels["NATIVE INDICATORS"].append(f"{symbol}  NOT REQUESTED | no fallback")

            seconds = int(stream["timeframe"]) * 60 if stream["timeframe"].isdigit() else 86400
            max_age = max(120, 2 * seconds)
            setups = summary.get("active_structures", {}).get("live_setups", ())[:3]
            setup_lines = [(f"Active: {setup['family']} / {setup['status']}", _level_text(setup.get("levels", {})))
                           for setup in setups]
            key_levels = {level["label"]: level["price"] for level in summary.get("key_levels", ())}
            prior_labels = ("PrevDayHi", "PrevDayLo") if daily else ("PDH", "PDL")
            if not any(label in key_levels for label in prior_labels):
                prior_labels = ("20B Hi", "20B Lo")
            levels = " · ".join(f"{label} {key_levels[label]:.8g}"
                                for label in ("SwHi", "SwLo", *prior_labels) if label in key_levels)

            current = []
            held = 0
            held_reason = ("quarantine" if counts else "fixed end" if fixed_end else
                           "stale/future bar" if freshness != "RECENT" else
                           "no usable acquisition" if acquisition in ("NO_RECEIPT", "NO_USABLE_BARS") else None)
            groups = stream["display"]["groups"]
            if previous is None:
                lines.append("  BASELINE: history loaded; no historical PA events announced as new.")
            else:
                for group in groups:
                    for event in group["events"]:
                        timestamp = parse_time(event["observed_at"])
                        if not previous < timestamp <= close or not self._record_id(event["id"]):
                            continue
                        if (held_reason or timestamp > now or (daily and timestamp != close)
                                or _bar_freshness(timestamp, now, max_age, daily) != "RECENT"):
                            held += 1
                            continue
                        current.append(event)
                if not current:
                    lines.append("  No new key PA event (display filter applied).")

            event_warning = " [DATA_QUALITY_UNKNOWN; exploratory]" if "DATA_QUALITY_UNKNOWN" in flags else ""
            tag = " [UNKNOWN]" if event_warning else ""
            for event in current:
                lines.append(f"  NEW PA{event_warning} {_ny(event['observed_at'])} | "
                             f"{event['family']} / {event['status']} / {event.get('direction', 'neutral')} "
                             f"| id={event['id']}")
                coords = _level_text(_setup_levels(event))
                if coords:
                    lines.append(f"    {coords}")
                if event.get("explanation"):
                    lines.append(f"    {event['explanation']}")

            recent = current[-1] if current else next(
                (group["events"][-1] for group in reversed(groups) if group["events"]), None)
            context_tail = []
            if recent:
                coords = _level_text(_setup_levels(recent))
                observed_at = _ny(recent["observed_at"])
                description = f"{recent['family']} / {recent['status']}"
                if current:
                    pa.append(f"NEW PA{tag} · {recent['family']} {recent['status']}")
                    context_tail.append(f"{recent.get('direction', 'neutral')} · {observed_at}")
                else:
                    pa.extend(("HISTORY · not new", description))
                    lines.append(f"  HISTORY (not new) {observed_at} | {description}")
                    context_tail.append(observed_at)
                    if coords:
                        lines.append(f"    {coords}")
                    if recent.get("explanation"):
                        lines.append(f"    {recent['explanation']}")
                if coords:
                    pa.append(coords)
                if recent.get("explanation"):
                    context_tail.append(recent["explanation"])
            else:
                pa.append("BASELINE · no new announcements" if previous is None else "No new key PA event")

            if levels:
                pa.append(f"Levels: {levels}")
                lines.append(f"  Levels: {levels}")
            pa.extend(description for description, _ in setup_lines)
            atr_clock = (len(pa), stale_detail) if use_native_atr else None
            if context_detail:
                pa.append(context_detail)
            if held:
                reason = held_reason or "older catch-up"
                lines.append(f"  Not announced as current: {held} display-filtered event(s) "
                             f"({reason}); journal evidence retained.")
                pa.append(f"Held {held} · {reason}")
            pa.extend(context_tail)
            for event in reversed(current[:-1]):
                coords = _level_text(_setup_levels(event))
                pa.append(f"NEW PA{tag} · {event['family']} {event['status']}")
                if coords:
                    pa.append(coords)
                if event.get("explanation"):
                    pa.append(event["explanation"])
            for description, coords in setup_lines:
                lines.append(f"  {description}" + (f" | {coords}" if coords else ""))
                if coords:
                    pa.append(coords)
            clock_slots.append((symbol, close, max_age, daily, market_row,
                                quality_row, readiness_row if not counts else None,
                                native_header, tuple(native_rows), atr_clock))
        return {"text": "\n".join(lines), "panels": panels, "round": self.round,
                "timestamp": parse_time(now).isoformat(), "source": source, "fixed_end": fixed_end,
                "risk": risk, "symbol_count": len(self.symbols), "clock_slots": tuple(clock_slots),
                "receipt": max(recorded_receipts, default=None)}


def terminal_output(requested, stream):
    """Use control sequences only on a capable terminal."""
    if requested in ("jsonl", "text"):
        return requested
    tty = stream.isatty()
    if requested == "tui":
        return "tui" if tty and os.environ.get("TERM", "") not in ("", "dumb") else "text"
    return "text" if tty else "jsonl"


_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def visible_width(value):
    return sum(_char_width(char) for char in _ANSI.sub("", value))


def _char_width(char):
    if unicodedata.combining(char) or unicodedata.category(char) in ("Cf", "Cc"):
        return 0
    return 2 if unicodedata.east_asian_width(char) in ("F", "W") else 1


def _take(value, limit):
    used = 0
    for index, char in enumerate(value):
        used += _char_width(char)
        if used > limit:
            return value[:index], value[index:]
    return value, ""


def _wrap(value, limit):
    value = "".join(c if unicodedata.category(c) != "Cc" else " " for c in _ANSI.sub("", value))
    while value:
        line, remaining = _take(value, limit)
        if remaining and not remaining.startswith(" ") and " " in line:
            prefix, tail = line.rsplit(" ", 1)
            # Prefer word boundaries without wasting most of a row.
            if visible_width(prefix) >= limit // 2:
                line, remaining = prefix, tail + remaining
        yield line.rstrip()
        value = remaining.lstrip()


def _panel(title, contents, width, height, accent, *, color):
    def paint(text, code):
        return f"\x1b[{code}m{text}\x1b[0m" if color else text
    inside = width - 4
    label = _take(title, inside)[0]
    body = [line for text in contents for line in _wrap(text, inside)]
    max_body = height - 2
    omitted = max(0, len(body) - max_body)
    body = body[:max_body]
    body += [""] * (max_body - len(body))
    top = "╭─ " + label + " " + "─" * (width - 5 - visible_width(label)) + "╮"
    rows = [paint(top, accent)]
    for raw in body:
        value = _take(raw, inside)[0]
        padding = " " * (inside - visible_width(value))
        emph = ("1;33" if any(tag in value for tag in ("STALE", "UNKNOWN", "QUARANTINE", "REVIEW"))
                else "1;92" if value.startswith("NEW PA") else None)
        rows.append(paint("│", "2") + " " + (paint(value, emph) if emph else value)
                    + padding + " " + paint("│", "2"))
    omission = f" +{omitted} lines omitted " if omitted else ""
    rows.append(paint("╰" + "─" + omission + "─" * (width - 3 - visible_width(omission)) + "╯", accent))
    return rows


def format_tui(view, *, width, height, color=False):
    """Return a resize-safe dashboard canvas without cursor/control commands."""
    def paint(text, code):
        return f"\x1b[{code}m{text}\x1b[0m" if color else text

    # The risk strip is based on every requested symbol, never the clipped panels.
    # On extremely narrow terminals use abbreviated labels while retaining all counts.
    risk_tags = [(label, count) for label, count in view["risk"].items() if count]
    risk = "RISK  " + (" · ".join(f"{label} {count}" for label, count in risk_tags)
                       if risk_tags else "no flagged symbols")
    if height < 6 or width < 16:
        short = {"QUARANTINE": "Q", "ERROR": "E", "UNKNOWN": "U", "STALE": "S"}
        risk = "RISK " + " ".join(f"{short[label]}{count}" for label, count in risk_tags)
    usable = max(1, min(160, width - 1))
    risk_rows = list(_wrap(risk, usable))
    clock_rows = view.get("clock_rows", ())
    compact = [*risk_rows, *(line for row in clock_rows for line in _wrap(row, usable)),
               _take("Enlarge terminal for 4 panels", usable)[0]]
    if width < 25 or height < (23 if width < 71 else 17):
        return "\n".join(compact[:max(1, height)])
    # Leave a spare column and row so terminals cannot auto-wrap/scroll the canvas.
    width, height = usable, height - 1
    header = f"PA OBSERVER  /  LIVE MONITOR   •   POLL {view['round']}"
    kind = "FIXED END" if view["fixed_end"] else "READ-ONLY"
    subtitle = f"{_ny(view['timestamp'])}   {kind}   {view['source']}" if not clock_rows else ""
    if clock_rows:
        subtitle = f"{clock_rows[0]}   {kind}"
    lines = [paint(_take(header, width)[0], "1;36"), *list(_wrap(subtitle, width))[:2],
             *(paint(line, "1;33" if risk_tags else "2") for line in risk_rows),
             *(line for row in clock_rows[1:] for line in _wrap(row, width))]
    names = list(view["panels"])
    accents = ("1;36", "1;35", "1;32", "1;33")
    remaining = height - len(lines) - 1
    if remaining < (6 if width >= 70 else 12):
        return "\n".join(compact[:max(1, height)])
    if width >= 70:
        left = (width - 2) // 2
        right = width - left - 2
        top = remaining // 2
        for idx, rows in ((0, top), (2, remaining - top)):
            a = _panel(names[idx], view["panels"][names[idx]], left, rows, accents[idx], color=color)
            b = _panel(names[idx+1], view["panels"][names[idx+1]], right, rows, accents[idx+1], color=color)
            lines.extend(x + "  " + y for x, y in zip(a, b))
    else:
        # On narrow windows put readiness near the top and use one honest, compact column.
        for index, idx in enumerate((0, 3, 2, 1)):
            count = remaining // 4 + int(index < remaining % 4)
            lines.extend(_panel(names[idx], view["panels"][names[idx]], width, count, accents[idx], color=color))
    footer = (f"{view['source']} · Ctrl-C stops" if clock_rows else
              "Closed bars only · Research only · Ctrl-C stops · text mode for full details")
    lines.append(_take(footer, width)[0])
    return "\n".join(lines)


def clock_frame(view, now, phase, pull_started):
    """Age the copied display only. No new bars, events, or provider deductions."""
    view = deepcopy(view)
    now = parse_time(now)
    walls = view["panels"]
    stale = 0
    for (symbol, close, limit, daily, market_row, quality_row, readiness_row,
         native_header, native_rows, atr_clock) in view["clock_slots"]:
        age = (now - close).total_seconds()
        freshness = _bar_freshness(close, now, limit, daily)
        stale += int(freshness != "RECENT")
        walls["MARKET"][market_row] = f"{_ny(close)}  |  {freshness}"
        walls["DATA QUALITY"][quality_row] = f"{symbol}  {freshness} | age {age:.0f}s"
        if freshness != "RECENT" and readiness_row is not None:
            walls["DATA QUALITY"][readiness_row] = "Snapshot no longer current"
        if freshness != "RECENT" and atr_clock is not None:
            index, line = atr_clock
            walls["PRICE ACTION"][index] = line
        if freshness != "RECENT" and native_rows:
            walls["NATIVE INDICATORS"][native_header] = f"{symbol}  {freshness} SNAPSHOT"
            for index, name in native_rows:
                walls["NATIVE INDICATORS"][index] = f"{name}  {freshness} (last pull)"
    view["risk"]["STALE"] = stale
    # Observation state never advances on a timer. Explicitly date the retained
    # PA and native snapshot and distinguish it from the currently running pull.
    timestamp = view.get("timestamp")
    age = (f"{max(0, int((now - parse_time(timestamp)).total_seconds()))}s old"
           if timestamp else "pending")

    def short(value):
        return _ny(value) if value else "—"

    view["clock_rows"] = (
        f"NY NOW {_ny(now)}  |  {phase}",
        f"Pull start {short(pull_started)} · Bars received {short(view.get('receipt'))} · Snapshot {age}",
    )
    return view


class TuiClock:
    """Own terminal redraws using only a detached main-thread snapshot."""

    def __init__(self, stream, *, source, symbols, fixed_end=False, clock=None,
                 size=None, tick_seconds=1, color=None):
        self._stream = stream
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._size = size or self._terminal_size
        self._tick = tick_seconds
        self._color = "NO_COLOR" not in os.environ if color is None else color
        self._condition = threading.Condition()
        self._phase = "CONNECTING"
        self._pull_started = None
        self._dirty = True
        self._closing = False
        waiting = [f"{symbol}  Awaiting first completed pull" for symbol in symbols]
        self._view = {"round": 0, "timestamp": None, "source": source, "fixed_end": fixed_end,
                      "panels": {name: waiting for name in (
                          "MARKET", "NATIVE INDICATORS", "PRICE ACTION", "DATA QUALITY")},
                      "risk": dict.fromkeys(("QUARANTINE", "ERROR", "UNKNOWN", "STALE"), 0),
                      "clock_slots": (), "receipt": None}
        self._thread = threading.Thread(target=self._draw_loop, name="pa-tui-clock", daemon=True)

    @property
    def running(self):
        return self._thread.is_alive()

    def _terminal_size(self):
        try:
            return os.get_terminal_size(self._stream.fileno())
        except (AttributeError, OSError, ValueError):
            return shutil.get_terminal_size(fallback=(80, 24))

    def start(self):
        self._thread.start()

    def status(self, phase, *, pull_started=None):
        self._enqueue(phase, pull_started=pull_started)

    def publish(self, view):
        self._enqueue("WAITING", view=deepcopy(view))

    def _enqueue(self, phase, *, pull_started=None, view=None):
        with self._condition:
            if self._closing:
                return
            self._phase = phase
            if pull_started is not None:
                self._pull_started = pull_started
            if view is not None:
                self._view = view
            self._dirty = True
            self._condition.notify()

    def close(self):
        with self._condition:
            self._closing = True
            self._condition.notify()
        if self._thread.ident is not None:
            self._thread.join()

    def _draw_loop(self):
        try:
            while True:
                with self._condition:
                    if not self._dirty and not self._closing:
                        self._condition.wait(self._tick)
                    if self._closing and not self._dirty:
                        return
                    view, phase, started = self._view, self._phase, self._pull_started
                    self._dirty = False
                size = self._size()
                snapshot = clock_frame(view, self._clock(), phase, started)
                canvas = format_tui(snapshot, width=size.columns, height=size.lines, color=self._color)
                self._stream.write("\x1b[2J\x1b[H" + canvas)
                self._stream.flush()
        except OSError:
            # Closing or losing the terminal does not change the acquired data.
            return
