"""Robinhood native technical-indicator contract, independent of local overlays."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import math
import re

from .timeframes import daily_close

INDICATORS = "get_equity_technical_indicators"
INTRADAY_SECONDS = {"15second": 15, "30second": 30, "minute": 60, "5minute": 300,
                    "10minute": 600, "30minute": 1800, "hour": 3600, "4hour": 14400}
INTERDAY_INTERVALS = frozenset({"day", "week", "month", "3month", "6month", "year",
                                "5year", "10year", "20year", "50year"})
INDICATOR_INTERVALS = frozenset(INTRADAY_SECONDS) | INTERDAY_INTERVALS

_PERIOD_ONLY = {
    "ema": 9, "sma": 9, "rsi": 14, "momentum": 12, "roc": 14, "cci": 14,
    "williams_r": 10, "atr": 14, "mfi": 14, "adx": 10, "donchian_channels": 20,
}
INDICATOR_DEFAULTS = {
    **{name: {"period": default} for name, default in _PERIOD_ONLY.items()},
    "bollinger_bands": {"period": 20, "num_std": 2},
    "macd": {"fast_period": 12, "slow_period": 26, "signal_period": 9},
    "keltner_channels": {"period": 20, "multiplier": 2},
    "supertrend": {"period": 10, "multiplier": 3},
    "vwap": {}, "obv": {}, "pivot_points": {"method": "classic"},
}
_CHANNELS = ("lower", "middle", "upper")
INDICATOR_FIELDS = dict.fromkeys(INDICATOR_DEFAULTS, ("value",)) | {
    "donchian_channels": _CHANNELS, "bollinger_bands": _CHANNELS, "keltner_channels": _CHANNELS,
    "macd": ("macd", "signal", "histogram"), "supertrend": ("value", "direction"),
    "pivot_points": ("pivot", "r1", "r2", "r3", "s1", "s2", "s3"),
}
_REQUEST_KEYS = frozenset({"symbols", "start_time", "end_time", "type", "interval",
                          "bounds", "adjustment_type", "output"})
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


@dataclass(frozen=True)
class IndicatorResult:
    series: tuple[dict, ...]
    raw_records: tuple[dict, ...]
    batches: tuple[dict, ...]
    quality: dict
    source: str
    cutoff: str


def _parameters(indicator_type, parameters):
    if not isinstance(indicator_type, str) or indicator_type not in INDICATOR_DEFAULTS:
        raise ValueError("unsupported Robinhood native indicator type")
    if not isinstance(parameters, dict) or not parameters.keys() <= INDICATOR_DEFAULTS[indicator_type].keys():
        raise ValueError("unexpected parameter for selected Robinhood indicator")
    for key, value in parameters.items():
        if key == "method":
            if value != "classic":
                raise ValueError("Robinhood pivot_points only supports classic")
        elif value is None:
            continue  # The live descriptor explicitly permits null numeric parameters.
        elif key.endswith("period"):
            if type(value) is not int or value <= 0:
                raise ValueError("indicator periods must be positive integers or null")
        elif (type(value) not in (int, float) or
              (type(value) is float and not math.isfinite(value)) or value <= 0):
            raise ValueError("indicator multipliers must be positive finite numbers or null")


def validate_indicator_request(args):
    # Local import avoids a cycle while this module is loaded by robinhood.
    from .robinhood import MAX_SYMBOLS, _symbols, _time
    if not isinstance(args, dict) or not _REQUEST_KEYS <= args.keys():
        raise ValueError("missing explicit Robinhood indicator request parameters")
    _parameters(args["type"], {k: v for k, v in args.items() if k not in _REQUEST_KEYS})
    if not isinstance(args["symbols"], list) or len(_symbols(args["symbols"])) > MAX_SYMBOLS:
        raise ValueError("Robinhood batch requires at most ten symbols")
    interval = args["interval"]
    if not isinstance(interval, str) or interval not in INDICATOR_INTERVALS:
        raise ValueError("unsupported Robinhood native interval (15minute is not native)")
    if args["bounds"] not in ("regular", "extended"):
        raise ValueError("Robinhood indicators require regular or extended bounds")
    adjust = args["adjustment_type"]
    if adjust not in ("none", "split", "all") or (adjust == "all" and interval not in INTERDAY_INTERVALS):
        raise ValueError("all adjustment requires day-or-coarser native indicators")
    output = args["output"]
    if not isinstance(output, str) or (output not in ("series", "latest") and
                                      not re.fullmatch(r"last:[1-9][0-9]*", output)):
        raise ValueError("indicator output must be series, latest, or last:N")
    if any(not isinstance(args[k], str) for k in ("start_time", "end_time")):
        raise ValueError("indicator request requires explicit RFC3339 bounds")
    if not _time(args["start_time"]) < _time(args["end_time"]):
        raise ValueError("indicator start must precede end")


def _boundary(value, *, end=False):
    from .robinhood import _time
    if isinstance(value, str) and _DATE.fullmatch(value):
        midnight = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
        return midnight + timedelta(days=int(end))
    return _time(value)


def _decimal_text(value):
    if value is None:
        return None
    if type(value) not in (str, float, int) or (type(value) is str and not _NUMBER.fullmatch(value)):
        raise ValueError("invalid indicator number")
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("invalid indicator number") from None
    if not number.is_finite():
        raise ValueError("invalid indicator number")
    return str(number)


def acquire_indicators(provider, symbols, start, end, indicator_type, interval, bounds,
                       adjustment_type, output, parameters):
    from .robinhood import MAX_BATCHES, MAX_BARS, MAX_SYMBOLS, RobinhoodError
    from .robinhood import _hash, _symbols, _time, _wire

    def mismatch():
        return RobinhoodError("ROBINHOOD_INDICATOR_RESPONSE_SCHEMA_MISMATCH")

    names = _symbols(symbols)
    if len(names) > MAX_BATCHES * MAX_SYMBOLS:
        raise ValueError("Robinhood indicator query exceeds maximum symbol batches")
    parameters = {} if parameters is None else parameters
    _parameters(indicator_type, parameters)
    parameters = {key: value for key, value in parameters.items() if value is not None}
    observed_before = _time(provider._clock())
    left = _boundary(start)
    right = _boundary(end, end=True) if end is not None else observed_before
    cutoff = min(right, observed_before)
    source = f"robinhood:native_indicator:{indicator_type}:{interval}:{bounds}:{adjustment_type}"
    common = {"start_time": _wire(left), "end_time": _wire(right), "type": indicator_type,
              "interval": interval, "bounds": bounds, "adjustment_type": adjustment_type,
              "output": output, **parameters}
    series, raw, batches = [], [], []
    can_normalize = interval in INTRADAY_SECONDS or (interval == "day" and bounds == "regular")
    quality = dict.fromkeys(("received", "emitted", "raw_only", "incomplete", "invalid", "out_of_range",
                             "duplicates", "undefined_values", "missing_fields"), 0)
    quality.update({"warmup": "unknown", "source_quality": "unknown",
                    "interpolation": "unknown", "window_sensitive": True, "snapshot_only": True,
                    "normalization_supported": can_normalize,
                    "not_found": [], "missing_symbols": [], "no_usable_symbols": []})
    fields = INDICATOR_FIELDS[indicator_type]
    seconds = INTRADAY_SECONDS.get(interval)
    for offset in range(0, len(names), MAX_SYMBOLS):
        group = names[offset:offset + MAX_SYMBOLS]
        args = {"symbols": list(group), **common}
        data, batch = provider._call(INDICATORS, args)
        rows, not_found = data["results"], data.get("not_found")
        rows = [] if rows is None else rows
        not_found = [] if not_found is None else not_found
        if (not isinstance(not_found, list) or any(not isinstance(n, str) or n not in group for n in not_found)
                or len(set(not_found)) != len(not_found)):
            raise mismatch()
        index = len(batches)
        delivered = set()
        local = dict.fromkeys(("received", "emitted", "raw_only", "incomplete", "invalid", "out_of_range",
                               "duplicates", "undefined_values", "missing_fields"), 0)
        for row in rows:
            if row is None:  # nullable item in live descriptor
                raw.append({"symbol": None, "batch": index, "result": None})
                continue
            if not isinstance(row, dict) or not isinstance(row.get("symbol"), str):
                raise mismatch()
            symbol = row["symbol"]
            if (symbol not in group or symbol in delivered or symbol in not_found
                    or row.get("interval") != interval or row.get("bounds") != bounds
                    or ("adjustment_type" in row and row["adjustment_type"] != adjustment_type)):
                raise mismatch()
            delivered.add(symbol)
            raw.append({"symbol": symbol, "batch": index, "result": deepcopy(row)})
            if "indicators" not in row:
                raise mismatch()
            details = row["indicators"]
            if details is None or details == [] or details == [None]:
                continue
            if (not isinstance(details, list) or len(details) != 1 or not isinstance(details[0], dict)
                    or details[0].get("type") != indicator_type or not isinstance(details[0].get("params"), dict)):
                raise mismatch()
            params = details[0]["params"]
            if any(v is not None and k in params and params[k] != v for k, v in parameters.items()):
                raise mismatch()
            if "series" not in details[0]:
                raise mismatch()
            items = details[0]["series"]
            items = [] if items is None else items
            if not isinstance(items, list) or len(items) > MAX_BARS:
                raise mismatch()
            id_record = {"symbol": symbol, "request": args, "params": params,
                         "received_at": batch["received_at"], "sent_at": batch["sent_at"],
                         "schema_sha256": batch["schema_sha256"], "response_sha256": batch["response_sha256"]}
            points, seen = [], {}
            for item in items:
                local["received"] += 1
                try:
                    opened = _time(item["begins_at"])
                except (KeyError, TypeError, ValueError, OverflowError):
                    local["invalid"] += 1
                    continue
                if not left <= opened < right:
                    local["out_of_range"] += 1
                    continue
                signature = _hash(item)
                if opened in seen:
                    if seen[opened] != signature:
                        raise RobinhoodError("ROBINHOOD_CONFLICTING_DUPLICATE_INDICATOR_POINT")
                    local["duplicates"] += 1
                    continue
                seen[opened] = signature
                if not can_normalize:
                    local["raw_only"] += 1
                    continue
                try:
                    if interval == "day":
                        if opened.hour or opened.minute or opened.second or opened.microsecond:
                            raise ValueError("daily indicator point must open at UTC midnight")
                        closed = daily_close(opened.date().isoformat())
                    else:
                        if opened.microsecond or opened.second % min(seconds, 60):
                            raise ValueError("indicator point is not aligned to native interval")
                        closed = opened + timedelta(seconds=seconds)
                    values = {key: _decimal_text(item.get(key)) for key in fields}
                except (ValueError, OverflowError):
                    local["invalid"] += 1
                    continue
                if closed > cutoff:
                    local["incomplete"] += 1
                    continue
                missing_fields = [key for key in fields if key not in item]
                local["missing_fields"] += len(missing_fields)
                local["undefined_values"] += sum(value is None for value in values.values())
                local["emitted"] += 1
                points.append({"begins_at": opened.isoformat(), "time": closed.isoformat(),
                               "values": values, "missing_fields": missing_fields})
            points.sort(key=lambda point: point["time"])
            series.append({"symbol": symbol, "indicator_type": indicator_type, "params": deepcopy(params),
                           "points": points, "latest": points[-1] if points else None,
                           "series_id": _hash(id_record), "batch": index, "source": source,
                           "interval": interval, "bounds": bounds, "adjustment_type": adjustment_type,
                           "warmup": "unknown", "source_quality": "unknown",
                           "normalization_supported": can_normalize})
        absent = sorted(set(group) - delivered)
        quality["missing_symbols"].extend(absent)
        quality["not_found"].extend(not_found)
        for key, count in local.items():
            quality[key] += count
        batch.update({"quality": local, "not_found": sorted(not_found), "missing_symbols": absent})
        batches.append(batch)
    quality["no_usable_symbols"] = sorted(set(names) - {
        r["symbol"] for r in series if any(
            v is not None for point in r["points"] for v in point["values"].values())
    })
    return IndicatorResult(tuple(series), tuple(raw), tuple(batches), quality, source, cutoff.isoformat())
