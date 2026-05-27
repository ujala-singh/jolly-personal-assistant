"""Tests for jolly.clients.github."""

from __future__ import annotations

import subprocess

import pytest

from jolly.clients import github
from jolly.clients.github import GhError, _summarize_checks


class TestSummarizeChecks:
    def test_empty_returns_none_status(self):
        assert _summarize_checks([])["status"] == "none"

    def test_all_passing(self):
        rollup = [{"conclusion": "SUCCESS"}, {"conclusion": "SUCCESS"}]
        result = _summarize_checks(rollup)
        assert result["status"] == "passing"
        assert result["total"] == 2
        assert result["passing"] == 2
        assert result["failing"] == 0

    def test_failing_dominates(self):
        rollup = [{"conclusion": "SUCCESS"}, {"conclusion": "FAILURE"}]
        result = _summarize_checks(rollup)
        assert result["status"] == "failing"
        assert result["failing"] == 1
        assert result["passing"] == 1

    def test_pending_when_no_failures(self):
        rollup = [{"conclusion": "SUCCESS"}, {"status": "IN_PROGRESS"}]
        result = _summarize_checks(rollup)
        assert result["status"] == "pending"

    def test_handles_legacy_state_field(self):
        rollup = [{"state": "FAILURE"}, {"state": "PENDING"}]
        result = _summarize_checks(rollup)
        assert result["status"] == "failing"


class TestMyOpenPrs:
    def test_enriches_each_pr(self, monkeypatch):
        def fake_gh_json(*args):
            if args[0] == "search":
                return [
                    {
                        "number": 7,
                        "title": "Fix thing",
                        "url": "https://github.com/o/r/pull/7",
                        "repository": {"nameWithOwner": "o/r"},
                        "updatedAt": "2026-05-27T10:00:00Z",
                        "isDraft": False,
                    }
                ]
            if args[0] == "pr" and args[1] == "view":
                return {
                    "statusCheckRollup": [{"conclusion": "SUCCESS"}],
                    "reviewDecision": "APPROVED",
                    "mergeable": "MERGEABLE",
                    "headRefName": "feat/x",
                }
            return None

        monkeypatch.setattr(github, "_gh_json", fake_gh_json)
        prs = github.my_open_prs()
        assert len(prs) == 1
        pr = prs[0]
        assert pr["repo"] == "o/r"
        assert pr["number"] == 7
        assert pr["reviewDecision"] == "APPROVED"
        assert pr["checks"]["status"] == "passing"
        assert pr["headRef"] == "feat/x"


class TestReviewRequests:
    def test_normalizes_search_result(self, monkeypatch):
        monkeypatch.setattr(
            github,
            "_gh_json",
            lambda *_a: [
                {
                    "number": 99,
                    "title": "Needs review",
                    "url": "https://github.com/o/r/pull/99",
                    "repository": {"nameWithOwner": "o/r"},
                    "author": {"login": "alice"},
                    "updatedAt": "2026-05-27T10:00:00Z",
                    "isDraft": True,
                }
            ],
        )
        result = github.review_requests()
        assert result == [
            {
                "number": 99,
                "title": "Needs review",
                "url": "https://github.com/o/r/pull/99",
                "repo": "o/r",
                "author": "alice",
                "updatedAt": "2026-05-27T10:00:00Z",
                "isDraft": True,
            }
        ]


class TestPrDiff:
    def test_returns_stdout_on_success(self, monkeypatch, completed):
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: completed(stdout="diff --git ..."))
        assert github.pr_diff("o/r", 1) == "diff --git ..."

    def test_raises_gh_error_on_failure(self, monkeypatch):
        def raise_called(*_a, **_kw):
            raise subprocess.CalledProcessError(1, "gh", stderr="boom")

        monkeypatch.setattr(subprocess, "run", raise_called)
        with pytest.raises(GhError, match="boom"):
            github.pr_diff("o/r", 1)


class TestGhJsonErrors:
    def test_missing_binary_raises(self, monkeypatch):
        def not_found(*_a, **_kw):
            raise FileNotFoundError()

        monkeypatch.setattr(subprocess, "run", not_found)
        with pytest.raises(GhError, match="not found"):
            github._gh_json("search", "prs")

    def test_nonzero_exit_raises(self, monkeypatch):
        def fail(*_a, **_kw):
            raise subprocess.CalledProcessError(1, "gh", output="", stderr="auth failed")

        monkeypatch.setattr(subprocess, "run", fail)
        with pytest.raises(GhError, match="auth failed"):
            github._gh_json("search", "prs")
