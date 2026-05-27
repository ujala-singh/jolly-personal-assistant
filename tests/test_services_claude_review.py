"""Tests for jolly.services.claude_review."""

from __future__ import annotations

import subprocess

from jolly.clients import github
from jolly.services import claude_review


class TestStartReview:
    def test_creates_pending_job(self, monkeypatch):
        # Prevent the worker thread from doing anything
        monkeypatch.setattr(
            claude_review.threading, "Thread", lambda **kw: type("T", (), {"start": lambda self: None})()
        )
        job_id = claude_review.start_review("o/r", 7)
        job = claude_review.get_job(job_id)
        assert job is not None
        assert job["status"] == "pending"
        assert job["repo"] == "o/r"
        assert job["number"] == 7
        assert job["result"] is None

    def test_get_unknown_returns_none(self):
        assert claude_review.get_job("nope") is None


class TestRunPath:
    def test_success_completes_with_result(self, monkeypatch, sync_threads, completed):
        monkeypatch.setattr(github, "pr_diff", lambda repo, n: "diff --git a/x b/x\n+added\n")
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: completed(stdout="LGTM\n"))
        job_id = claude_review.start_review("o/r", 1)
        job = claude_review.get_job(job_id)
        assert job["status"] == "done"
        assert job["result"] == "LGTM"
        assert job["finishedAt"] is not None

    def test_empty_diff_records_error(self, monkeypatch, sync_threads):
        monkeypatch.setattr(github, "pr_diff", lambda repo, n: "   \n")
        job_id = claude_review.start_review("o/r", 1)
        job = claude_review.get_job(job_id)
        assert job["status"] == "error"
        assert "empty diff" in job["error"]

    def test_claude_not_on_path(self, monkeypatch, sync_threads):
        monkeypatch.setattr(github, "pr_diff", lambda repo, n: "diff body")

        def missing(*_a, **_kw):
            raise FileNotFoundError()

        monkeypatch.setattr(subprocess, "run", missing)
        job_id = claude_review.start_review("o/r", 1)
        job = claude_review.get_job(job_id)
        assert job["status"] == "error"
        assert "claude" in job["error"].lower()

    def test_claude_nonzero_exit_records_error(self, monkeypatch, sync_threads):
        monkeypatch.setattr(github, "pr_diff", lambda repo, n: "diff body")

        def fail(*_a, **_kw):
            raise subprocess.CalledProcessError(1, "claude", output="", stderr="rate limit")

        monkeypatch.setattr(subprocess, "run", fail)
        job_id = claude_review.start_review("o/r", 1)
        job = claude_review.get_job(job_id)
        assert job["status"] == "error"
        assert "rate limit" in job["error"]

    def test_timeout_records_error(self, monkeypatch, sync_threads):
        monkeypatch.setattr(github, "pr_diff", lambda repo, n: "diff body")

        def slow(*_a, **_kw):
            raise subprocess.TimeoutExpired("claude", 240)

        monkeypatch.setattr(subprocess, "run", slow)
        job_id = claude_review.start_review("o/r", 1)
        job = claude_review.get_job(job_id)
        assert job["status"] == "error"
        assert "timed out" in job["error"]
