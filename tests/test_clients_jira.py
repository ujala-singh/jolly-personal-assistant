"""Tests for jolly.clients.jira."""

from __future__ import annotations

import base64

import httpx
import pytest

from jolly.clients import jira
from jolly.clients.jira import JiraError


@pytest.fixture
def jira_enabled(override_config):
    return override_config(
        jira_base_url="https://example.atlassian.net",
        jira_email="me@example.com",
        jira_api_token="tok",
        jira_sprint_field="customfield_10020",
    )


class TestAuthHeader:
    def test_builds_basic_auth(self, jira_enabled):
        header = jira._auth_header()
        assert header.startswith("Basic ")
        decoded = base64.b64decode(header.split(" ", 1)[1]).decode()
        assert decoded == "me@example.com:tok"


class TestDisabledGuards:
    def test_my_open_issues_raises_when_disabled(self, override_config):
        override_config(jira_base_url="", jira_email="", jira_api_token="")
        with pytest.raises(JiraError, match="not configured"):
            jira.my_open_issues()


class TestNormalize:
    def test_extracts_core_fields(self, jira_enabled):
        raw = {
            "key": "PROJ-1",
            "fields": {
                "summary": "Do thing",
                "status": {"name": "In Progress", "statusCategory": {"key": "indeterminate"}},
                "priority": {"name": "High"},
                "updated": "2026-05-27T10:00:00.000+0000",
                "customfield_10020": [],
            },
        }
        result = jira._normalize(raw, "customfield_10020")
        assert result["key"] == "PROJ-1"
        assert result["url"] == "https://example.atlassian.net/browse/PROJ-1"
        assert result["summary"] == "Do thing"
        assert result["status"] == "In Progress"
        assert result["statusCategory"] == "indeterminate"
        assert result["priority"] == "High"
        assert result["inActiveSprint"] is False

    def test_detects_active_sprint(self, jira_enabled):
        raw = {
            "key": "PROJ-2",
            "fields": {
                "summary": "S",
                "status": {"name": "To Do", "statusCategory": {"key": "new"}},
                "priority": None,
                "updated": "t",
                "customfield_10020": [
                    {"state": "closed", "name": "Old"},
                    {"state": "active", "name": "Current"},
                ],
            },
        }
        result = jira._normalize(raw, "customfield_10020")
        assert result["inActiveSprint"] is True

    def test_handles_missing_fields_gracefully(self, jira_enabled):
        raw = {"key": "PROJ-3", "fields": {}}
        result = jira._normalize(raw, "customfield_10020")
        assert result["status"] is None
        assert result["priority"] is None
        assert result["inActiveSprint"] is False


class TestMyOpenIssues:
    def test_posts_to_search_jql(self, monkeypatch, jira_enabled, fake_response):
        captured = {}

        def fake_post(url, *, json, headers, timeout):
            captured["url"] = url
            captured["body"] = json
            return fake_response(
                json_data={
                    "issues": [
                        {
                            "key": "PROJ-1",
                            "fields": {
                                "summary": "x",
                                "status": {"name": "Open", "statusCategory": {"key": "new"}},
                                "priority": None,
                                "updated": "t",
                                "customfield_10020": None,
                            },
                        }
                    ]
                }
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        result = jira.my_open_issues()
        assert captured["url"].endswith("/rest/api/3/search/jql")
        assert "currentUser()" in captured["body"]["jql"]
        assert result[0]["key"] == "PROJ-1"


class TestTransitions:
    def test_returns_list(self, monkeypatch, jira_enabled, fake_response):
        monkeypatch.setattr(
            httpx,
            "get",
            lambda *a, **kw: fake_response(
                json_data={
                    "transitions": [
                        {"id": "11", "name": "Start", "to": {"name": "In Progress"}},
                        {"id": "21", "name": "Done", "to": {"name": "Done"}},
                    ]
                }
            ),
        )
        result = jira.transitions("PROJ-1")
        assert result == [
            {"id": "11", "name": "Start", "to": "In Progress"},
            {"id": "21", "name": "Done", "to": "Done"},
        ]


class TestApplyTransition:
    def test_posts_transition_id(self, monkeypatch, jira_enabled, fake_response):
        captured = {}

        def fake_post(url, *, json, headers, timeout):
            captured["url"] = url
            captured["body"] = json
            return fake_response(status_code=204, content=b"")

        monkeypatch.setattr(httpx, "post", fake_post)
        jira.transition("PROJ-1", "31")
        assert captured["url"].endswith("/rest/api/3/issue/PROJ-1/transitions")
        assert captured["body"] == {"transition": {"id": "31"}}
