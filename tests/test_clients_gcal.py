"""Tests for jolly.clients.gcal (ICS feed-based)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import httpx
import pytest
from icalendar import Calendar, Event

from jolly.clients import gcal
from jolly.clients.gcal import GcalError, _short_url, _to_event, week_dates


@pytest.fixture
def gcal_enabled(override_config):
    return override_config(gcal_ics_urls=("https://calendar.example.com/private-xxx/basic.ics",))


class TestWeekDates:
    def test_known_date_layout(self):
        # 2026-05-27 is a Wednesday → Monday should be 2026-05-25
        days = week_dates(date(2026, 5, 27))
        assert [d["label"] for d in days] == ["Mon", "Tue", "Wed", "Thu", "Fri"]
        assert days[0]["date"] == "2026-05-25"
        assert days[4]["date"] == "2026-05-29"
        assert days[2]["isToday"] is True
        assert sum(d["isToday"] for d in days) == 1

    def test_today_outside_weekdays_marks_none(self):
        # Saturday 2026-05-30 → no day in Mon-Fri matches
        days = week_dates(date(2026, 5, 30))
        assert sum(d["isToday"] for d in days) == 0


class TestIsAvailable:
    def test_false_without_urls(self, override_config):
        override_config(gcal_ics_urls=())
        assert gcal.is_available() is False

    def test_true_with_urls(self, gcal_enabled):
        assert gcal.is_available() is True


class TestToEvent:
    def test_timed_event(self):
        ev = Event()
        ev.add("summary", "Standup")
        ev.add("dtstart", datetime(2026, 5, 27, 9, 0, tzinfo=UTC))
        ev.add("dtend", datetime(2026, 5, 27, 9, 30, tzinfo=UTC))
        ev.add("url", "https://meet.example/abc")
        ev.add("location", "Zoom")
        result = _to_event(ev)
        assert result["allDay"] is False
        assert result["title"] == "Standup"
        assert result["link"] == "https://meet.example/abc"
        assert result["location"] == "Zoom"
        assert result["startTime"] != ""
        assert result["endTime"] != ""

    def test_all_day_event(self):
        ev = Event()
        ev.add("summary", "Holiday")
        ev.add("dtstart", date(2026, 5, 29))
        ev.add("dtend", date(2026, 5, 30))
        result = _to_event(ev)
        assert result["allDay"] is True
        assert result["startTime"] == ""
        assert result["startDate"] == "2026-05-29"

    def test_handles_missing_dtend(self):
        ev = Event()
        ev.add("summary", "Brief")
        ev.add("dtstart", datetime(2026, 5, 27, 9, 0, tzinfo=UTC))
        result = _to_event(ev)
        assert result["title"] == "Brief"


class TestShortUrl:
    def test_truncates_ical_path(self):
        url = "https://calendar.google.com/calendar/ical/longuser@x.com/private-token/basic.ics"
        assert _short_url(url).endswith("…")

    def test_short_url_returns_short(self):
        assert _short_url("short") == "short"


class TestWeekSchedule:
    def test_raises_when_disabled(self, override_config):
        override_config(gcal_ics_urls=())
        with pytest.raises(GcalError, match="GCAL_ICS_URLS"):
            gcal.week_schedule(today=date(2026, 5, 27))

    def test_fetches_and_expands_recurring(self, monkeypatch, gcal_enabled, fake_response):
        cal = Calendar()
        cal.add("prodid", "-//test//en")
        cal.add("version", "2.0")

        # Recurring daily standup, 10 occurrences starting Mon
        ev_recur = Event()
        ev_recur.add("summary", "Daily standup")
        ev_recur.add("dtstart", datetime(2026, 5, 25, 9, 0, tzinfo=UTC))
        ev_recur.add("dtend", datetime(2026, 5, 25, 9, 15, tzinfo=UTC))
        ev_recur.add("rrule", {"freq": "DAILY", "count": 10})
        ev_recur.add("uid", "recur@x")
        cal.add_component(ev_recur)

        # One-off on Wed
        ev_one = Event()
        ev_one.add("summary", "1:1")
        ev_one.add("dtstart", datetime(2026, 5, 27, 14, 0, tzinfo=UTC))
        ev_one.add("dtend", datetime(2026, 5, 27, 15, 0, tzinfo=UTC))
        ev_one.add("uid", "one@x")
        cal.add_component(ev_one)

        ics_text = cal.to_ical().decode()
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: fake_response(text=ics_text))

        events = gcal.week_schedule(today=date(2026, 5, 27))
        titles = [e["title"] for e in events]
        # 5 standup occurrences Mon-Fri + 1 one-off
        assert titles.count("Daily standup") == 5
        assert "1:1" in titles
        # Sorted by date then time
        dates = [e["startDate"] for e in events]
        assert dates == sorted(dates)

    def test_propagates_fetch_errors(self, monkeypatch, gcal_enabled):
        def boom(*_a, **_kw):
            raise httpx.ConnectError("network down", request=None)

        monkeypatch.setattr(httpx, "get", boom)
        with pytest.raises(GcalError):
            gcal.week_schedule(today=date(2026, 5, 27))
