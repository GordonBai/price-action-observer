"""Daily observations close at the XNYS session close (with legacy next-UTC-midnight compatibility)."""
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import re
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
_SESSION = re.compile(r"\d{4}-\d{2}-\d{2}")


@lru_cache(maxsize=1)
def calendar():
    import exchange_calendars
    return exchange_calendars.get_calendar("XNYS")


def daily_close(session_label: str) -> datetime:
    if not isinstance(session_label, str) or not _SESSION.fullmatch(session_label) or not calendar().is_session(session_label):
        raise ValueError("daily label is not an XNYS trading session")
    return calendar().session_close(session_label).to_pydatetime().astimezone(timezone.utc)


def daily_session(closed: datetime) -> str:
    if not isinstance(closed, datetime) or closed.tzinfo is None or closed.utcoffset() is None:
        raise ValueError("daily close must be an aware datetime")
    utc = closed.astimezone(timezone.utc)
    ny_label = utc.astimezone(NY).date().isoformat()
    if calendar().is_session(ny_label) and utc == daily_close(ny_label):
        return ny_label
    if not (utc.hour or utc.minute or utc.second or utc.microsecond):
        legacy = (utc.date() - timedelta(days=1)).isoformat()
        if calendar().is_session(legacy):
            return legacy
    raise ValueError("daily close must match XNYS session close or legacy next UTC midnight")


def consecutive_daily(old: datetime, new: datetime) -> bool:
    old_session, new_session = daily_session(old), daily_session(new)
    return new > old and calendar().next_session(old_session).date().isoformat() == new_session


def is_daily_fresh(closed: datetime, now: datetime, grace_seconds: int = 7200) -> bool:
    session = daily_session(closed)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be an aware datetime")
    utc_closed = closed.astimezone(timezone.utc)
    utc_now = now.astimezone(timezone.utc)
    if utc_closed > utc_now + timedelta(seconds=5):
        return False
    ny_today = utc_now.astimezone(NY).date()
    lookback = timedelta(days=max(14, int(grace_seconds // 86400) + 14))
    sessions = calendar().sessions_in_range((ny_today - lookback).isoformat(), ny_today.isoformat())
    grace = timedelta(seconds=grace_seconds)
    required = [s.date().isoformat() for s in sessions if daily_close(s.date().isoformat()) + grace <= utc_now]
    return not required or session >= required[-1]


def next_daily_close(now: datetime, settle_seconds: float = 10) -> float:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be an aware datetime")
    utc_now = now.astimezone(timezone.utc)
    ny_today = utc_now.astimezone(NY).date()
    sessions = calendar().sessions_in_range(ny_today.isoformat(), (ny_today + timedelta(days=14)).isoformat())
    settle = timedelta(seconds=settle_seconds)
    for s in sessions:
        target = daily_close(s.date().isoformat()) + settle
        if target > utc_now:
            return (target - utc_now).total_seconds()
    raise ValueError("no upcoming XNYS session close found")
