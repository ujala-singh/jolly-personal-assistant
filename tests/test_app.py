"""Tests for jolly.app Flask routes."""

from __future__ import annotations

import json

from jolly import app as app_mod
from jolly.clients import jira, linear
from jolly.services import claude_review


def _empty_snapshot() -> dict:
    return {
        "tickets": {"all": [], "daily": []},
        "prs": {"mine": [], "reviewRequests": []},
        "calendar": {"enabled": False, "days": [], "events": []},
        "sources": {"jira": False, "linear": False, "gcal": False},
        "errors": {},
    }


class TestIndex:
    def test_serves_html_with_brand(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert b"jolly" in r.data.lower()
        assert b"refresh" in r.data

    def test_serves_favicon(self, client):
        r = client.get("/static/favicon.svg")
        assert r.status_code == 200
        assert b"<svg" in r.data
        assert r.mimetype == "image/svg+xml"


class TestDashboardJson:
    def test_returns_snapshot_shape(self, client, monkeypatch):
        monkeypatch.setattr(app_mod.dashboard, "snapshot", _empty_snapshot)
        r = client.get("/api/dashboard")
        assert r.status_code == 200
        body = r.get_json()
        assert set(body) >= {"tickets", "prs", "calendar", "sources", "errors"}


class TestTicketTransitions:
    def test_linear_requires_team_id(self, client):
        r = client.get("/api/tickets/linear/abc/transitions")
        assert r.status_code == 400
        assert "teamId" in r.get_json()["error"]

    def test_linear_lists_states(self, client, monkeypatch):
        monkeypatch.setattr(
            linear, "workflow_states", lambda team_id: [{"id": "s1", "name": "Todo", "type": "unstarted"}]
        )
        r = client.get("/api/tickets/linear/abc/transitions?teamId=t1")
        assert r.status_code == 200
        assert r.get_json()["transitions"][0]["name"] == "Todo"

    def test_jira_lists_transitions(self, client, monkeypatch):
        monkeypatch.setattr(
            jira, "transitions", lambda key: [{"id": "11", "name": "Start", "to": "In Progress"}]
        )
        r = client.get("/api/tickets/jira/PROJ-1/transitions")
        assert r.status_code == 200
        assert r.get_json()["transitions"][0]["id"] == "11"

    def test_unknown_source_returns_400(self, client):
        r = client.get("/api/tickets/asana/X/transitions")
        assert r.status_code == 400

    def test_post_transition_requires_target_id(self, client):
        r = client.post(
            "/api/tickets/jira/PROJ-1/transition",
            data="{}",
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_post_transition_jira_success(self, client, monkeypatch):
        called = {}
        monkeypatch.setattr(jira, "transition", lambda k, t: called.setdefault("args", (k, t)))
        r = client.post(
            "/api/tickets/jira/PROJ-1/transition",
            data=json.dumps({"targetId": "11"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert called["args"] == ("PROJ-1", "11")

    def test_post_transition_linear_success(self, client, monkeypatch):
        monkeypatch.setattr(
            linear,
            "transition",
            lambda i, s: {"success": True, "issue": {"id": i, "state": {"name": "Done"}}},
        )
        r = client.post(
            "/api/tickets/linear/abc/transition",
            data=json.dumps({"targetId": "state-id"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert r.get_json()["success"] is True


class TestReviewEndpoints:
    def test_start_review_returns_job_id(self, client, monkeypatch):
        monkeypatch.setattr(claude_review, "start_review", lambda repo, n: "abc123")
        r = client.post("/api/prs/o/r/7/review")
        assert r.status_code == 200
        assert r.get_json() == {"jobId": "abc123"}

    def test_get_unknown_review_404(self, client):
        r = client.get("/api/reviews/missing-id")
        assert r.status_code == 404

    def test_get_review_returns_job_state(self, client):
        # Seed a job directly into the in-memory store
        claude_review._jobs["xyz"] = {
            "id": "xyz",
            "status": "done",
            "result": "ok",
            "repo": "o/r",
            "number": 1,
            "createdAt": "t",
            "finishedAt": "t",
            "error": None,
        }
        r = client.get("/api/reviews/xyz")
        assert r.status_code == 200
        assert r.get_json()["status"] == "done"
        assert r.get_json()["result"] == "ok"
