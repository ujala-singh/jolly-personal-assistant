"""Google Calendar via private ICS feed URLs.

No OAuth — each Google Calendar exposes a private "secret address in iCal format".
Multiple calendars supported via comma-separated URLs in `GCAL_ICS_URLS`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import httpx
import recurring_ical_events
from icalendar import Calendar

from jolly.config import config


class GcalError(RuntimeError):
    pass


def is_available() -> bool:
    return config.gcal_enabled


def week_dates(today: date | None = None) -> list[dict]:
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    labels = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    return [
        {
            "date": (monday + timedelta(days=i)).isoformat(),
            "label": labels[i],
            "isToday": (monday + timedelta(days=i)) == today,
        }
        for i in range(5)
    ]


def week_schedule(today: date | None = None) -> list[dict]:
    if not is_available():
        raise GcalError("GCAL_ICS_URLS not set in .env")
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    saturday = monday + timedelta(days=5)

    events: list[dict] = []
    errors: list[str] = []
    for url in config.gcal_ics_urls:
        try:
            events.extend(_fetch_one(url, monday, saturday))
        except Exception as exc:
            errors.append(f"{_short_url(url)}: {exc}")

    if errors and not events:
        raise GcalError("; ".join(errors))

    events.sort(key=lambda e: (e["startDate"], e["startTime"] or ""))
    return events


def _fetch_one(url: str, start: date, end: date) -> list[dict]:
    response = httpx.get(url, timeout=15, follow_redirects=True)
    response.raise_for_status()
    cal = Calendar.from_ical(response.text)
    occurrences = recurring_ical_events.of(cal).between(start, end)
    return [_to_event(occ) for occ in occurrences]


def _to_event(component) -> dict:
    dtstart_prop = component.get("dtstart")
    dtend_prop = component.get("dtend")
    dtstart = dtstart_prop.dt if dtstart_prop else None
    dtend = dtend_prop.dt if dtend_prop else dtstart

    summary = str(component.get("summary") or "").strip()
    url = str(component.get("url") or "").strip()
    location = str(component.get("location") or "").strip()

    if isinstance(dtstart, datetime):
        start_local = dtstart.astimezone() if dtstart.tzinfo else dtstart
        end_local = (
            dtend.astimezone() if isinstance(dtend, datetime) and dtend.tzinfo else dtend
        ) or start_local
        return {
            "startDate": start_local.date().isoformat(),
            "startTime": start_local.strftime("%H:%M"),
            "endDate": (end_local.date() if isinstance(end_local, datetime) else end_local).isoformat(),
            "endTime": end_local.strftime("%H:%M") if isinstance(end_local, datetime) else "",
            "title": summary,
            "link": url,
            "location": location,
            "allDay": False,
        }
    # all-day (date, not datetime)
    start_d: date = dtstart  # type: ignore[assignment]
    end_d: date = dtend if isinstance(dtend, date) else start_d  # type: ignore[assignment]
    return {
        "startDate": start_d.isoformat(),
        "startTime": "",
        "endDate": end_d.isoformat(),
        "endTime": "",
        "title": summary,
        "link": url,
        "location": location,
        "allDay": True,
    }


def _short_url(url: str) -> str:
    if "/calendar/ical/" in url:
        tail = url.split("/calendar/ical/", 1)[1]
        return tail.split("/")[0][:20] + "…"
    return url[:30] + "…" if len(url) > 30 else url
