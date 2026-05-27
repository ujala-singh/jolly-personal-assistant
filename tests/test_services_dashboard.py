"""Tests for jolly.services.dashboard."""

from __future__ import annotations

import pytest

from jolly.services import dashboard


class TestIsDaily:
    @pytest.mark.parametrize("state_type", ["started", "inprogress", "in-progress", "indeterminate"])
    def test_in_progress_states_qualify(self, state_type):
        assert dashboard._is_daily({"inActiveCycle": False, "stateType": state_type}) is True

    def test_active_cycle_qualifies(self):
        assert dashboard._is_daily({"inActiveCycle": True, "stateType": "todo"}) is True

    @pytest.mark.parametrize("state_type", ["todo", "backlog", "completed", "done", "canceled"])
    def test_non_in_progress_disqualifies(self, state_type):
        assert dashboard._is_daily({"inActiveCycle": False, "stateType": state_type}) is False

    def test_missing_state_type_disqualifies(self):
        assert dashboard._is_daily({"inActiveCycle": False, "stateType": None}) is False


class TestMergeTickets:
    def test_combines_and_sorts_by_updated_desc(self):
        linear = [
            {
                "id": "L1",
                "identifier": "L-1",
                "title": "lin",
                "url": "u",
                "updatedAt": "2026-05-25T10:00:00Z",
                "priorityLabel": "Low",
                "state": {"name": "Todo", "type": "unstarted"},
                "cycle": {"name": "C1", "isActive": True},
                "team": {"id": "t", "key": "L"},
            },
        ]
        jira = [
            {
                "key": "J-1",
                "summary": "jira",
                "url": "u",
                "status": "In Progress",
                "statusCategory": "indeterminate",
                "priority": "High",
                "updated": "2026-05-27T10:00:00Z",
                "inActiveSprint": False,
            }
        ]
        merged = dashboard._merge_tickets(linear, jira)
        assert [t["key"] for t in merged] == ["J-1", "L-1"]  # newer first
        assert merged[1]["source"] == "linear"
        assert merged[1]["inActiveCycle"] is True
        assert merged[0]["source"] == "jira"


class TestSnapshot:
    def test_aggregates_with_all_sources_off(self, monkeypatch, override_config):
        override_config(jira_email="", jira_api_token="", linear_api_key="", gcal_ics_urls=())
        monkeypatch.setattr(dashboard.github, "my_open_prs", lambda: [])
        monkeypatch.setattr(dashboard.github, "review_requests", lambda: [])
        snap = dashboard.snapshot()
        assert snap["tickets"]["all"] == []
        assert snap["tickets"]["daily"] == []
        assert snap["prs"]["mine"] == []
        assert snap["calendar"]["enabled"] is False
        assert snap["sources"] == {"jira": False, "linear": False, "gcal": False}
        assert snap["errors"] == {}

    def test_aggregates_all_sources_enabled(self, monkeypatch, override_config):
        override_config(
            jira_base_url="https://x",
            jira_email="me",
            jira_api_token="t",
            linear_api_key="k",
            gcal_ics_urls=("https://x.ics",),
        )
        monkeypatch.setattr(dashboard.github, "my_open_prs", lambda: [{"number": 1}])
        monkeypatch.setattr(dashboard.github, "review_requests", lambda: [{"number": 2}])
        monkeypatch.setattr(
            dashboard.linear,
            "my_open_issues",
            lambda: [
                {
                    "id": "L1",
                    "identifier": "L-1",
                    "title": "lin",
                    "url": "u",
                    "updatedAt": "2026-05-25T10:00:00Z",
                    "priorityLabel": None,
                    "state": {"name": "In Progress", "type": "started"},
                    "cycle": {"name": "C1", "isActive": True},
                    "team": {"id": "t", "key": "L"},
                }
            ],
        )
        monkeypatch.setattr(dashboard.jira, "my_open_issues", lambda: [])
        monkeypatch.setattr(dashboard.gcal, "is_available", lambda: True)
        monkeypatch.setattr(
            dashboard.gcal, "week_schedule", lambda: [{"startDate": "2026-05-27", "title": "Meet"}]
        )
        snap = dashboard.snapshot()
        assert len(snap["tickets"]["all"]) == 1
        assert len(snap["tickets"]["daily"]) == 1  # started + active cycle
        assert snap["calendar"]["events"] == [{"startDate": "2026-05-27", "title": "Meet"}]
        assert snap["prs"]["mine"] == [{"number": 1}]

    def test_collects_source_errors_without_blocking(self, monkeypatch, override_config):
        override_config(jira_base_url="https://x", jira_email="m", jira_api_token="t", linear_api_key="")

        def boom():
            raise RuntimeError("oh no")

        monkeypatch.setattr(dashboard.github, "my_open_prs", boom)
        monkeypatch.setattr(dashboard.github, "review_requests", lambda: [])
        monkeypatch.setattr(dashboard.jira, "my_open_issues", lambda: [])
        snap = dashboard.snapshot()
        assert "github_prs" in snap["errors"]
        assert "oh no" in snap["errors"]["github_prs"]
        assert snap["prs"]["mine"] == []
