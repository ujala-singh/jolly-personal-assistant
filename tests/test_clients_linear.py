"""Tests for jolly.clients.linear."""

from __future__ import annotations

import httpx
import pytest

from jolly.clients import linear
from jolly.clients.linear import LinearError


@pytest.fixture
def linear_enabled(override_config):
    return override_config(linear_api_key="lin_test_key")


class TestLinearAuth:
    def test_raises_when_key_missing(self, override_config):
        override_config(linear_api_key="")
        with pytest.raises(LinearError, match="LINEAR_API_KEY"):
            linear.my_open_issues()

    def test_sends_authorization_header(self, monkeypatch, linear_enabled, fake_response):
        captured = {}

        def fake_post(url, *, json, headers, timeout):
            captured["headers"] = headers
            return fake_response(json_data={"data": {"viewer": {"assignedIssues": {"nodes": []}}}})

        monkeypatch.setattr(httpx, "post", fake_post)
        linear.my_open_issues()
        assert captured["headers"]["Authorization"] == "lin_test_key"


class TestMyOpenIssues:
    def test_filters_completed_and_canceled(self, monkeypatch, linear_enabled, fake_response):
        nodes = [
            {
                "id": "1",
                "identifier": "X-1",
                "title": "todo",
                "url": "https://x",
                "updatedAt": "t",
                "priorityLabel": None,
                "state": {"id": "s1", "name": "Todo", "type": "unstarted", "color": "#aaa"},
                "cycle": None,
                "team": {"id": "t", "key": "X", "name": "X"},
            },
            {
                "id": "2",
                "identifier": "X-2",
                "title": "done",
                "url": "https://x",
                "updatedAt": "t",
                "priorityLabel": None,
                "state": {"id": "s2", "name": "Done", "type": "completed", "color": "#bbb"},
                "cycle": None,
                "team": {"id": "t", "key": "X", "name": "X"},
            },
            {
                "id": "3",
                "identifier": "X-3",
                "title": "cancelled",
                "url": "https://x",
                "updatedAt": "t",
                "priorityLabel": None,
                "state": {"id": "s3", "name": "Cancelled", "type": "canceled", "color": "#ccc"},
                "cycle": None,
                "team": {"id": "t", "key": "X", "name": "X"},
            },
        ]
        monkeypatch.setattr(
            httpx,
            "post",
            lambda *a, **kw: fake_response(
                json_data={"data": {"viewer": {"assignedIssues": {"nodes": nodes}}}}
            ),
        )
        result = linear.my_open_issues()
        assert [i["identifier"] for i in result] == ["X-1"]


class TestWorkflowStates:
    def test_returns_normalized_nodes(self, monkeypatch, linear_enabled, fake_response):
        nodes = [
            {"id": "s1", "name": "Todo", "type": "unstarted"},
            {"id": "s2", "name": "In Progress", "type": "started"},
        ]
        monkeypatch.setattr(
            httpx,
            "post",
            lambda *a, **kw: fake_response(json_data={"data": {"workflowStates": {"nodes": nodes}}}),
        )
        assert linear.workflow_states("team-id") == nodes


class TestTransition:
    def test_returns_issue_update_payload(self, monkeypatch, linear_enabled, fake_response):
        payload = {
            "data": {
                "issueUpdate": {
                    "success": True,
                    "issue": {"id": "i", "state": {"id": "s", "name": "Done", "type": "completed"}},
                }
            }
        }
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: fake_response(json_data=payload))
        result = linear.transition("i", "s")
        assert result["success"] is True
        assert result["issue"]["state"]["name"] == "Done"


class TestErrorPath:
    def test_graphql_errors_field_raises(self, monkeypatch, linear_enabled, fake_response):
        monkeypatch.setattr(
            httpx,
            "post",
            lambda *a, **kw: fake_response(json_data={"errors": [{"message": "bad query"}]}),
        )
        with pytest.raises(LinearError, match="Linear API errors"):
            linear.my_open_issues()
