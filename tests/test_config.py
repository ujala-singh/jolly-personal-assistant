"""Tests for jolly.config."""

from __future__ import annotations

import pytest

from jolly.config import Config, _parse_urls


def _make(**overrides) -> Config:
    base: dict = {
        "jira_base_url": "",
        "jira_email": "",
        "jira_api_token": "",
        "jira_sprint_field": "customfield_10020",
        "linear_api_key": "",
        "gcal_ics_urls": (),
        "port": 8765,
        "poll_seconds": 300,
    }
    base.update(overrides)
    return Config(**base)


class TestEnabledFlags:
    def test_jira_disabled_when_any_field_missing(self):
        assert _make(jira_base_url="https://x", jira_email="me@x").jira_enabled is False
        assert _make(jira_base_url="https://x", jira_api_token="t").jira_enabled is False

    def test_jira_enabled_with_all_three(self):
        cfg = _make(jira_base_url="https://x", jira_email="me@x", jira_api_token="t")
        assert cfg.jira_enabled is True

    def test_linear_enabled_with_key(self):
        assert _make(linear_api_key="").linear_enabled is False
        assert _make(linear_api_key="lin_xxx").linear_enabled is True

    def test_gcal_enabled_with_any_url(self):
        assert _make(gcal_ics_urls=()).gcal_enabled is False
        assert _make(gcal_ics_urls=("https://x.ics",)).gcal_enabled is True


class TestParseUrls:
    def test_empty_string(self):
        assert _parse_urls("") == ()

    def test_single_url(self):
        assert _parse_urls("https://a.ics") == ("https://a.ics",)

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("a,b,c", ("a", "b", "c")),
            (" a , b , c ", ("a", "b", "c")),
            ("a,,b,", ("a", "b")),
            (",,,", ()),
        ],
    )
    def test_comma_separated_variants(self, raw, expected):
        assert _parse_urls(raw) == expected
