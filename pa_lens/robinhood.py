"""Read-only Robinhood acquisition. No login, execution, or fallback paths."""

from contextlib import contextmanager, ExitStack
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import importlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Callable

from .core import Bar
from .provider_indicators import INDICATORS, acquire_indicators, validate_indicator_request
from .timeframes import daily_close

HISTORICALS = "get_equity_historicals"
QUOTES = "get_equity_quotes"
INTERVAL_MINUTES = {"minute": 1, "5minute": 5, "10minute": 10,
                    "30minute": 30, "hour": 60, "4hour": 240}
BOUNDS = frozenset({"regular", "extended", "trading", "24_5", "24_7", "hyper_trading"})
MAX_SYMBOLS = 10
MAX_BATCHES = 128
MAX_BARS = 5000
_HISTORY_KEYS = frozenset({"symbols", "start_time", "end_time", "interval",
                           "bounds", "adjustment_type"})
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.\-]{0,19}")
_RFC3339 = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})")


class RobinhoodError(RuntimeError):
    """A sanitized acquisition error safe to report to a CLI user."""


@dataclass(frozen=True)
class FetchResult:
    bars: tuple[Bar, ...]
    raw_records: tuple[dict, ...]
    batches: tuple[dict, ...]
    quality: dict
    source: str
    cutoff: str
    bar_provenance: tuple[dict, ...]


@dataclass(frozen=True)
class QuoteResult:
    raw_records: tuple[dict, ...]
    batches: tuple[dict, ...]
    quality: dict


def _time(value):
    if isinstance(value, str) and _RFC3339.fullmatch(value):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("an aware datetime or RFC3339 timestamp is required")
    return value.astimezone(timezone.utc)


def _wire(value):
    return value.isoformat().replace("+00:00", "Z")


def _symbols(values):
    if isinstance(values, (str, bytes, dict)):
        raise ValueError("symbols must be a collection of equity symbols")
    try:
        names = tuple(values)
    except TypeError:
        raise ValueError("symbols must be a collection of equity symbols") from None
    if not names or any(not isinstance(x, str) or not _SYMBOL.fullmatch(x) for x in names):
        raise ValueError("invalid equity symbol; expected uppercase ticker")
    if len(set(names)) != len(names):
        raise ValueError("duplicate requested symbol")
    return names


def _options(interval, bounds, adjustment):
    if not isinstance(interval, str) or interval not in {*INTERVAL_MINUTES, "day"}:
        raise ValueError("unsupported Robinhood interval")
    if not isinstance(bounds, str) or bounds not in BOUNDS:
        raise ValueError("unsupported Robinhood bounds")
    if interval == "day" and bounds != "regular":
        raise ValueError("daily analysis requires regular bounds")
    if adjustment not in ("none", "split", "all") or (interval != "day" and adjustment == "all"):
        raise ValueError("unsupported Robinhood adjustment type for this interval")


def _span(interval):
    # Leave one bucket to accommodate an inclusive upstream end boundary.
    return timedelta(minutes=INTERVAL_MINUTES.get(interval, 1440) * (MAX_BARS - 1))


def _validate_request(tool, args):
    if tool == INDICATORS:
        return validate_indicator_request(args)
    allowed = {"symbols"} if tool == QUOTES else _HISTORY_KEYS if tool == HISTORICALS else None
    if allowed is None or not isinstance(args, dict) or args.keys() != allowed:
        raise ValueError("Robinhood request is not an allowlisted read")
    if not isinstance(args["symbols"], list) or len(_symbols(args["symbols"])) > MAX_SYMBOLS:
        raise ValueError("Robinhood batch requires at most ten symbols")
    if tool == HISTORICALS:
        _options(args["interval"], args["bounds"], args["adjustment_type"])
        if any(not isinstance(args[k], str) for k in ("start_time", "end_time")):
            raise ValueError("Robinhood request requires explicit RFC3339 bounds")
        start, end = _time(args["start_time"]), _time(args["end_time"])
        if not start < end or end - start > _span(args["interval"]):
            raise ValueError("Robinhood request exceeds permitted range")


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _transport_failure(exc, fallback="ROBINHOOD_READ_UNAVAILABLE"):
    message = str(exc)
    if "INTERACTIVE_AUTH_OR_APPROVAL_REQUIRED" in message:
        return RobinhoodError("ROBINHOOD_AUTH_REQUIRED")
    return RobinhoodError(fallback)


def _results(payload, *, indicators=False):
    if not isinstance(payload, dict) or payload.get("isError"):
        raise RobinhoodError("ROBINHOOD_READ_FAILED")
    if "structuredContent" in payload:
        payload = payload["structuredContent"]
    elif "data" not in payload and isinstance(payload.get("content"), list):
        blocks = payload["content"]
        if (len(blocks) != 1 or not isinstance(blocks[0], dict) or
                blocks[0].get("type") != "text" or not isinstance(blocks[0].get("text"), str)):
            raise RobinhoodError("ROBINHOOD_RESPONSE_SCHEMA_MISMATCH")
        try:
            payload = json.loads(blocks[0]["text"])
        except ValueError:
            raise RobinhoodError("ROBINHOOD_RESPONSE_SCHEMA_MISMATCH") from None
    data = payload.get("data") if isinstance(payload, dict) else None
    if (not isinstance(data, dict) or "results" not in data or
            (not isinstance(data["results"], list) and not (indicators and data["results"] is None))):
        raise RobinhoodError("ROBINHOOD_RESPONSE_SCHEMA_MISMATCH")
    if indicators and not any(data.get(key) for key in ("errors", "restricted")):
        return data
    if any(data.get(key) for key in ("errors", "not_found", "restricted")):
        raise RobinhoodError("ROBINHOOD_PROVIDER_ERROR_OR_RESTRICTED_RESULT")
    return data["results"]


def _normalized(symbol, timeframe, closed, row, source):
    prices = []
    for field in ("open_price", "high_price", "low_price", "close_price"):
        price = row.get(field)
        if not isinstance(price, str):
            raise ValueError("invalid price type")
        try:
            value = Decimal(price)
            if not value.is_finite() or value <= 0:
                raise ValueError("invalid price")
            prices.append(value)
        except InvalidOperation:
            raise ValueError("invalid price") from None
    o, h, l, c = prices
    if h < max(o, c, l) or l > min(o, c):
        raise ValueError("invalid OHLC ordering")
    volume = row.get("volume")
    if type(volume) is not int or volume < 0:
        raise ValueError("invalid integer volume")
    return Bar(symbol, str(timeframe), closed.isoformat(), *map(float, prices), volume, source)


class RobinhoodProvider:
    """Validated read adapter, injectable without an authenticated environment."""

    def __init__(self, transport: Callable, *, descriptors=None, clock=None):
        self._transport = transport
        self._descriptors = None if descriptors is None else deepcopy(descriptors)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _call(self, tool, args):
        _validate_request(tool, args)
        descriptor = self._descriptors.get(tool) if self._descriptors is not None else None
        if descriptor is None and self._descriptors is not None:
            raise RobinhoodError("ROBINHOOD_READ_TOOL_UNAVAILABLE")
        request = deepcopy(args)
        sent = _time(self._clock())
        try:
            reply = self._transport(tool, deepcopy(args))
        except Exception as exc:
            raise _transport_failure(exc) from None
        received = _time(self._clock())
        try:
            schema_hash = _hash(descriptor) if descriptor is not None else None
            response_hash = _hash(reply)
        except (TypeError, ValueError, OverflowError):
            raise RobinhoodError("ROBINHOOD_RESPONSE_SCHEMA_MISMATCH") from None
        return _results(reply, indicators=tool == INDICATORS), {"tool": tool, "request": request, "sent_at": sent.isoformat(),
                                 "received_at": received.isoformat(), "schema_sha256": schema_hash,
                                 "response_sha256": response_hash}

    def fetch(self, symbols, start, end, *, interval="minute", bounds="regular",
              adjustment_type="split", accept_unknown=False):
        """Read original OHLCV; return only provably closed, usable closed bars."""
        if type(accept_unknown) is not bool:
            raise ValueError("accept_unknown must be a boolean")
        names = _symbols(symbols)
        _options(interval, bounds, adjustment_type)
        start, end = _time(start), _time(end)
        if not start < end:
            raise ValueError("historical start must be before end")
        span = _span(interval)
        groups = tuple(names[i:i + MAX_SYMBOLS] for i in range(0, len(names), MAX_SYMBOLS))
        n_windows, remainder = divmod(end - start, span)
        if (n_windows + bool(remainder)) * len(groups) > MAX_BATCHES:
            raise ValueError("Robinhood query exceeds maximum batch count; narrow the range or symbols")
        cutoff = min(end, _time(self._clock()))
        source = f"robinhood:{interval}:{bounds}:{adjustment_type}"
        if accept_unknown:
            source += ":accept_unknown"
        minutes = INTERVAL_MINUTES.get(interval)
        duration = None if minutes is None else timedelta(minutes=minutes)
        bars, raw, batches = [], [], []
        provenance = {}
        counts = ("received", "emitted", "interpolated", "invalid", "incomplete",
                  "duplicates", "out_of_range",
                  "not_interpolated", "interpolation_unknown", "unknown_emitted")
        quality = dict.fromkeys(counts, 0)
        quality.update({"interpolated_opens": {}, "interpolation_unknown_opens": {}, "missing_results": [],
                        "no_usable_symbols": [], "daily_normalization_supported": True,
                        "accept_unknown": accept_unknown})
        seen = {}

        left = start
        while left < end:
            right = end if end - left <= span else left + span
            for group in groups:
                args = {"symbols": list(group), "interval": interval, "bounds": bounds,
                        "adjustment_type": adjustment_type, "start_time": _wire(left),
                        "end_time": _wire(right)}
                rows, batch = self._call(HISTORICALS, args)
                index = len(batches)
                local = dict.fromkeys(counts, 0)
                delivered = set()
                for row in rows:
                    if not isinstance(row, dict) or not isinstance(row.get("symbol"), str):
                        raise RobinhoodError("ROBINHOOD_RESPONSE_SCHEMA_MISMATCH")
                    symbol = row["symbol"]
                    if (symbol not in group or symbol in delivered or row.get("interval") != interval
                            or row.get("bounds") != bounds
                            or ("adjustment_type" in row and row["adjustment_type"] != adjustment_type)
                            or not isinstance(row.get("bars"), list) or len(row["bars"]) > MAX_BARS):
                        raise RobinhoodError("ROBINHOOD_RESPONSE_SCHEMA_MISMATCH")
                    delivered.add(symbol)
                    for item in row["bars"]:
                        local["received"] += 1
                        raw.append({"symbol": symbol, "batch": index, "bar": deepcopy(item)})
                        try:
                            opened = _time(item["begins_at"])
                        except (KeyError, TypeError, ValueError, OverflowError):
                            local["invalid"] += 1
                            continue
                        # Inclusive seam only, never accept a bar outside its request.
                        if not left <= opened <= right or not start <= opened < end:
                            local["out_of_range"] += 1
                            continue
                        key = (symbol, opened)
                        fingerprint = _hash(item)
                        if key in seen:
                            if seen[key] != fingerprint:
                                raise RobinhoodError("ROBINHOOD_CONFLICTING_DUPLICATE_BAR")
                            local["duplicates"] += 1
                            continue
                        seen[key] = fingerprint
                        if item.get("interpolated") is True:
                            local["interpolated"] += 1
                            quality["interpolated_opens"].setdefault(symbol, []).append(opened.isoformat())
                            continue
                        unknown = item.get("interpolated") is not False
                        if unknown:
                            local["interpolation_unknown"] += 1
                            quality["interpolation_unknown_opens"].setdefault(symbol, []).append(opened.isoformat())
                            if not accept_unknown or "interpolated" in item:
                                continue
                        else:
                            local["not_interpolated"] += 1
                        if (opened.second or opened.microsecond
                                or (minutes is None and (opened.hour or opened.minute))
                                or (bounds == "regular" and item.get("session") != "reg")):
                            local["invalid"] += 1
                            continue
                        try:
                            closed = daily_close(opened.date().isoformat()) if minutes is None else opened + duration
                        except ValueError:
                            local["invalid"] += 1
                            continue
                        if cutoff < closed:
                            local["incomplete"] += 1
                            continue
                        try:
                            normalized = _normalized(symbol, minutes or "D", closed, item, source)
                        except (ValueError, OverflowError):
                            local["invalid"] += 1
                            continue
                        bars.append(normalized)
                        provenance[(symbol, normalized.time)] = {
                            "symbol": symbol, "time": normalized.time, "opened_at": opened.isoformat(),
                            "batch": index, "session": item.get("session"),
                            **({"session_date": opened.date().isoformat()} if minutes is None else {}),
                            "interpolation": "unknown" if unknown else "explicit_false",
                            "quality": "DATA_QUALITY_UNKNOWN" if unknown else "INTERPOLATION_EXPLICIT_FALSE",
                        }
                        local["emitted"] += 1
                        local["unknown_emitted"] += int(unknown)
                missing = sorted(set(group) - delivered)
                if missing:
                    quality["missing_results"].append({"batch": index, "symbols": missing})
                batch.update({"quality": local, "missing_symbols": missing})
                batches.append(batch)
                for key, count in local.items():
                    quality[key] += count
            left = right
        quality["no_usable_symbols"] = sorted(set(names) - {bar.symbol for bar in bars})
        for field in ("interpolated_opens", "interpolation_unknown_opens"):
            for opens in quality[field].values():
                opens.sort()
        bars.sort(key=lambda bar: (bar.time, bar.symbol))
        quality["status"] = ("DATA_QUALITY_UNKNOWN" if quality["interpolation_unknown"]
                             else "NO_UNKNOWN_INTERPOLATION_MARKERS")
        return FetchResult(tuple(bars), tuple(raw), tuple(batches), quality, source, cutoff.isoformat(),
                           tuple(provenance[(b.symbol, b.time)] for b in bars))

    def indicators(self, symbols, start, end, indicator_type, interval, bounds="regular",
                   adjustment_type="split", output="series", parameters=None):
        """Read one native calculation per symbol over the exact supplied window."""
        return acquire_indicators(self, symbols, start, end, indicator_type, interval, bounds,
                                  adjustment_type, output, parameters)

    def quotes(self, symbols):
        """Retrieve quote evidence without creating, repairing, or pricing any bar."""
        names = _symbols(symbols)
        if len(names) > MAX_BATCHES * MAX_SYMBOLS:
            raise ValueError("Robinhood quote query exceeds maximum batch count")
        raw, batches, missing = [], [], []
        for i in range(0, len(names), MAX_SYMBOLS):
            chunk = names[i:i + MAX_SYMBOLS]
            rows, batch = self._call(QUOTES, {"symbols": list(chunk)})
            delivered = set()
            for row in rows:
                quote = row.get("quote") if isinstance(row, dict) else None
                symbol = quote.get("symbol") if isinstance(quote, dict) else None
                if not isinstance(symbol, str) or symbol not in chunk or symbol in delivered:
                    raise RobinhoodError("ROBINHOOD_RESPONSE_SCHEMA_MISMATCH")
                delivered.add(symbol)
                raw.append(deepcopy(row))
            absent = sorted(set(chunk) - delivered)
            missing.extend(absent)
            batch.update({"missing_symbols": absent, "quality": {"received": len(delivered)}})
            batches.append(batch)
        return QuoteResult(tuple(raw), tuple(batches), {"received": len(raw), "missing_symbols": sorted(missing)})


@contextmanager
def open_robinhood(*, infra_root=None, binary="codex", timeout=30):
    """Borrow the installed official app-server transport, never log in automatically."""
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Robinhood timeout must be positive and finite")
    with ExitStack() as stack:
        expected = None
        if infra_root is not None:
            source = (Path(infra_root).expanduser() / "src").resolve()
            expected = source / "trading_execution" / "transport.py"
            if not expected.is_file():
                raise RobinhoodError("ROBINHOOD_INFRA_UNAVAILABLE")
            path = str(source)
            if path not in sys.path:
                sys.path.insert(0, path)
                stack.callback(sys.path.remove, path)
        try:
            module = importlib.import_module("trading_execution.transport")
            if expected is not None and Path(module.__file__).resolve() != expected.resolve():
                raise RobinhoodError("ROBINHOOD_INFRA_PATH_MISMATCH")
            transport_type = module.CodexMarketTransport
        except (ImportError, AttributeError, TypeError):
            raise RobinhoodError("ROBINHOOD_INFRA_UNAVAILABLE") from None
        try:
            transport = stack.enter_context(transport_type(binary=binary, timeout=timeout))
            descriptors = {k: v for k, v in transport.tool_descriptors.items()
                           if k in (HISTORICALS, QUOTES, INDICATORS)}
            if not descriptors:
                raise RobinhoodError("ROBINHOOD_READ_TOOL_UNAVAILABLE")
            read = transport._read_call
        except RobinhoodError:
            raise
        except Exception as exc:
            raise _transport_failure(exc) from None
        # This private entry point is needed for explicit historical intervals
        # beyond the legacy convenience validator. _call enforces our own schema.
        yield RobinhoodProvider(read, descriptors=descriptors)
