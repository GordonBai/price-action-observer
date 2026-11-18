"""Daily observations become available at the UTC midnight AFTER the session."""
from datetime import timedelta
from functools import lru_cache

@lru_cache(maxsize=1)
def calendar():
    import exchange_calendars
    return exchange_calendars.get_calendar("XNYS")

def daily_session(closed):
    if closed.hour or closed.minute or closed.second or closed.microsecond:
        raise ValueError("daily availability must be next UTC midnight")
    label=(closed.date()-timedelta(days=1)).isoformat()
    if not calendar().is_session(label):
        raise ValueError("daily label is not an XNYS trading session")
    return label

def consecutive_daily(old,new):
    return calendar().next_session(daily_session(old)).date().isoformat()==daily_session(new)
