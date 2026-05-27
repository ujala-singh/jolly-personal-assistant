"""Environment-backed configuration. Loaded once at import time."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    jira_base_url: str
    jira_email: str
    jira_api_token: str
    jira_sprint_field: str
    linear_api_key: str
    gcal_ics_urls: tuple[str, ...]
    port: int
    poll_seconds: int

    @property
    def jira_enabled(self) -> bool:
        return bool(self.jira_base_url and self.jira_email and self.jira_api_token)

    @property
    def linear_enabled(self) -> bool:
        return bool(self.linear_api_key)

    @property
    def gcal_enabled(self) -> bool:
        return bool(self.gcal_ics_urls)


def _parse_urls(raw: str) -> tuple[str, ...]:
    return tuple(url.strip() for url in raw.split(",") if url.strip())


def _load() -> Config:
    return Config(
        jira_base_url=os.getenv("JIRA_BASE_URL", "").rstrip("/"),
        jira_email=os.getenv("JIRA_EMAIL", ""),
        jira_api_token=os.getenv("JIRA_API_TOKEN", ""),
        jira_sprint_field=os.getenv("JIRA_SPRINT_FIELD", "customfield_10020"),
        linear_api_key=os.getenv("LINEAR_API_KEY", ""),
        gcal_ics_urls=_parse_urls(os.getenv("GCAL_ICS_URLS", "")),
        port=int(os.getenv("PORT", "8765")),
        poll_seconds=int(os.getenv("POLL_SECONDS", "300")),
    )


config = _load()
