"""Shared fixtures for jolly tests."""

from __future__ import annotations

import dataclasses
import json
from types import SimpleNamespace
from typing import Any

import pytest

from jolly import config as cfg_module
from jolly.app import create_app
from jolly.services import claude_review


# ---------------------------------------------------------------------------
# Flask app + client
# ---------------------------------------------------------------------------
@pytest.fixture
def app():
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Config override — Config is frozen, so we swap the bound reference in each
# module that imported it.
# ---------------------------------------------------------------------------
_CONFIG_CONSUMERS = (
    "jolly.config",
    "jolly.clients.gcal",
    "jolly.clients.linear",
    "jolly.clients.jira",
    "jolly.services.dashboard",
)


@pytest.fixture
def override_config(monkeypatch):
    def _apply(**fields: Any):
        new_cfg = dataclasses.replace(cfg_module.config, **fields)
        for mod_path in _CONFIG_CONSUMERS:
            mod = __import__(mod_path, fromlist=["config"])
            if hasattr(mod, "config"):
                monkeypatch.setattr(f"{mod_path}.config", new_cfg, raising=False)
        return new_cfg

    return _apply


# ---------------------------------------------------------------------------
# Claude review — wipe job dict between tests, run threads synchronously.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def clear_claude_jobs():
    claude_review._jobs.clear()
    yield
    claude_review._jobs.clear()


@pytest.fixture
def sync_threads(monkeypatch):
    """Replace threading.Thread with a synchronous stand-in for deterministic tests."""

    class _SyncThread:
        def __init__(self, target, args=(), kwargs=None, daemon=False):
            self._target = target
            self._args = args
            self._kwargs = kwargs or {}

        def start(self):
            self._target(*self._args, **self._kwargs)

    monkeypatch.setattr(claude_review.threading, "Thread", _SyncThread)


# ---------------------------------------------------------------------------
# HTTP response stand-in for monkeypatching httpx.get / httpx.post
# ---------------------------------------------------------------------------
class FakeResponse:
    def __init__(
        self, status_code: int = 200, json_data: Any = None, text: str = "", content: bytes | None = None
    ):
        self.status_code = status_code
        self._json = json_data
        if json_data is not None:
            self.text = json.dumps(json_data)
        else:
            self.text = text
        self.content = content if content is not None else self.text.encode()

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


@pytest.fixture
def fake_response():
    return FakeResponse


# ---------------------------------------------------------------------------
# subprocess.run stand-in
# ---------------------------------------------------------------------------
def make_completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


@pytest.fixture
def completed():
    return make_completed
