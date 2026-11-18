"""Human projection of current read-only polling, not another signal engine."""
from collections import deque
import os
import re
import unicodedata

from .core import parse_time

_SEEN_LIMIT = 4096


def _utc(value):
    return parse_time(value).isoformat().replace("+00:00", "Z")


def _period(value):
    return value + "m" if value.isdigit() else value


def _native_lines(context):
    lines = [f"  Native context: {context.get('status', 'UNAVAILABLE')} (warmup/source quality unknown)"]
    if context.get("reason"):
        lines.append(f"    {context['reason']}")
    for key, name in (("ema20", "EMA20"), ("rsi14", "RSI14")):
        row = context.get(key)
        if not row:
            continue
        if row.get("status") == "AVAILABLE_SOURCE_UNKNOWN":
            relation = f" (close {row['relation']})" if row.get("relation") else ""
            lines.append(f"    {name}={row.get('value')}{relation}; effective {_utc(row['effective_at'])}")
        else:
            suffix = f": {row['reason']}" if row.get("reason") else ""
            lines.append(f"    {name}: {row.get('status', 'UNAVAILABLE')}{suffix}")
    return lines


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
        line = (f"[{_utc(now)}] Robinhood read-only monitor | poll {self.round} | "
                f"{source} | research only")
        lines = [line + (" | FIXED END (not following live)" if fixed_end else "")]
        panels = {key: [] for key in ("MARKET", "NATIVE INDICATORS", "PRICE ACTION", "DATA QUALITY")}
        streams = {s["symbol"]: s for s in snapshot["streams"] if s["source"] == source}
        acquisitions = {s: r for symbols, r in receipts for s in symbols}
        transport_errors = {entry["symbol"] for entry in snapshot.get("transport", ())
                            if entry["source"] == source and entry.get("status") == "error"}
        risk = dict.fromkeys(("QUARANTINE", "ERROR", "UNKNOWN", "STALE"), 0)
        for symbol in self.symbols:
            stream = streams.get(symbol)
            result = acquisitions.get(symbol, {})
            acquisition = result.get("status", "NO_RECEIPT")
            if symbol in result.get("quality", {}).get("no_usable_symbols", []):
                acquisition = "NO_USABLE_BARS"
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
            lines.append(f"  Latest journaled {_period(stream['timeframe'])} closed bar {_utc(close)} "
                         f"| O={last['open']} H={last['high']} L={last['low']} C={last['close']} V={last['volume']}")
            status = f"  {freshness} | age={stream['age_seconds']:.0f}s | {stream['readiness']}"
            panels["MARKET"].extend((f"{symbol}  {_period(stream['timeframe'])} CLOSED",
                                     f"{_utc(close)}  |  {freshness}",
                                     f"O {last['open']}   H {last['high']}",
                                     f"L {last['low']}   C {last['close']}   V {last['volume']}"))
            if flags:
                status += " | " + " / ".join(dict.fromkeys(flags))
            lines.append(status)
            panels["DATA QUALITY"].extend((f"{symbol}  {freshness} | age {stream['age_seconds']:.0f}s",
                                           *dict.fromkeys(flags or [acquisition])))
            if flags and acquisition not in flags:
                panels["DATA QUALITY"].append(f"Acquisition: {acquisition}")
            if stream["readiness"] not in (*flags, freshness, acquisition):
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
            context = stream["state"].get("context", "unavailable")
            lines.append(f"  PA context: {context} (first-received bars; not a trade signal)")
            panels["PRICE ACTION"].append(f"{symbol}  {context}")
            native = stream.get("native_interpretation", {})
            if native_enabled:
                lines.extend(_native_lines(native))
                panels["NATIVE INDICATORS"].append(f"{symbol}  {native.get('status', 'UNAVAILABLE')}")
                for key, name in (("ema20", "EMA20"), ("rsi14", "RSI14")):
                    entry = native.get(key, {})
                    if entry.get("status") == "AVAILABLE_SOURCE_UNKNOWN":
                        relation = f" | close {entry['relation']}" if entry.get("relation") else ""
                        panels["NATIVE INDICATORS"].append(f"{name} {entry.get('value')}{relation}")
                    else:
                        panels["NATIVE INDICATORS"].append(f"{name}  {entry.get('status', 'UNAVAILABLE')}")
                panels["NATIVE INDICATORS"].append("Warmup / source quality unknown")
                reasons = list(dict.fromkeys(r for r in (
                    native.get("reason"), native.get("ema20", {}).get("reason"),
                    native.get("rsi14", {}).get("reason")) if r))
                panels["NATIVE INDICATORS"].extend(reasons[:2])
            else:
                lines.append("  Native context: NOT REQUESTED; no local fallback.")
                panels["NATIVE INDICATORS"].append(f"{symbol}  NOT REQUESTED | no fallback")

            def history():
                groups = stream["display"]["groups"]
                prior = next((group["events"][-1] for group in reversed(groups) if group["events"]), None)
                if prior:
                    observed_at = _utc(prior["observed_at"])
                    description = f"{prior['family']} / {prior['status']}"
                    lines.append(f"  HISTORY (not new) {observed_at} | {description}")
                    panels["PRICE ACTION"].extend(("HISTORY · not new",
                                                   description, observed_at))
                    if prior.get("explanation"):
                        lines.append(f"    {prior['explanation']}")
                        panels["PRICE ACTION"].append(prior["explanation"])
            if previous is None:
                lines.append("  BASELINE: history loaded; no historical PA events announced as new.")
                panels["PRICE ACTION"].append("BASELINE · no new announcements")
                history()
                continue
            seconds = int(stream["timeframe"]) * 60 if stream["timeframe"].isdigit() else 86400
            max_age = max(120, 2 * seconds)
            current = []
            held = 0
            held_reason = ("quarantine" if counts else "fixed end" if fixed_end else
                           "stale/future bar" if freshness != "RECENT" else
                           "no usable acquisition" if acquisition in ("NO_RECEIPT", "NO_USABLE_BARS") else None)
            for group in stream["display"]["groups"]:
                for event in group["events"]:
                    timestamp = parse_time(event["observed_at"])
                    if not previous < timestamp <= close or not self._record_id(event["id"]):
                        continue
                    age = (now - timestamp).total_seconds()
                    if held_reason or not 0 <= age <= max_age:
                        held += 1
                        continue
                    current.append(event)
            if not current:
                lines.append("  No new key PA event (display filter applied).")
                panels["PRICE ACTION"].append("No new key PA event")
            event_warning = " [DATA_QUALITY_UNKNOWN; exploratory]" if "DATA_QUALITY_UNKNOWN" in flags else ""
            for event in current:
                lines.append(f"  NEW PA{event_warning} {_utc(event['observed_at'])} | "
                             f"{event['family']} / {event['status']} / {event.get('direction', 'neutral')} "
                             f"| id={event['id']}")
                if event.get("explanation"):
                    lines.append(f"    {event['explanation']}")
            if current:
                latest = current[-1]
                extra = f" (+{len(current) - 1})" if len(current) > 1 else ""
                tag = " [UNKNOWN]" if event_warning else ""
                panels["PRICE ACTION"].extend((f"NEW PA{tag} · {latest['family']}{extra}",
                    f"{latest['status']} / {latest.get('direction', 'neutral')}",
                    _utc(latest["observed_at"])))
                if latest.get("explanation"):
                    panels["PRICE ACTION"].append(latest["explanation"])
            if held:
                lines.append(f"  Not announced as current: {held} display-filtered event(s) "
                             f"({held_reason or 'older catch-up'}); journal evidence retained.")
                panels["PRICE ACTION"].append(f"Held {held} · {held_reason or 'older catch-up'}")
            if not current:
                history()
        return {"text": "\n".join(lines), "panels": panels, "round": self.round,
                "timestamp": _utc(now), "source": source, "fixed_end": fixed_end,
                "risk": risk, "symbol_count": len(self.symbols)}


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
    compact = [*risk_rows, _take("Enlarge terminal for 4 panels", usable)[0]]
    if width < 25 or height < (23 if width < 71 else 17):
        return "\n".join(compact[:max(1, height)])
    # Leave a spare column and row so terminals cannot auto-wrap/scroll the canvas.
    width, height = usable, height - 1
    header = f"PA OBSERVER  /  LIVE MONITOR   •   POLL {view['round']}"
    kind = "FIXED END" if view["fixed_end"] else "READ-ONLY"
    subtitle = f"{view['timestamp']}   {kind}   {view['source']}"
    lines = [paint(_take(header, width)[0], "1;36"), *list(_wrap(subtitle, width))[:2],
             *(paint(line, "1;33" if risk_tags else "2") for line in risk_rows)]
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
    lines.append(_take("Closed bars only   ·   Research only   ·   Ctrl-C stops   ·   text mode for full details", width)[0])
    return "\n".join(lines)
