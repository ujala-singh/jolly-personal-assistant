"""Jira Cloud REST v3 client. Uses Basic auth with email + API token."""

from __future__ import annotations

import base64

import httpx

from jolly.config import config


class JiraError(RuntimeError):
    pass


def _auth_header() -> str:
    creds = f"{config.jira_email}:{config.jira_api_token}"
    return "Basic " + base64.b64encode(creds.encode()).decode()


def _headers() -> dict[str, str]:
    return {
        "Authorization": _auth_header(),
        "Accept": "application/json",
    }


def _check_enabled() -> None:
    if not config.jira_enabled:
        raise JiraError("Jira not configured (JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN)")


def _get(path: str, params: dict | None = None) -> dict:
    _check_enabled()
    response = httpx.get(
        f"{config.jira_base_url}{path}",
        params=params,
        headers=_headers(),
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def _post(path: str, body: dict) -> dict | None:
    _check_enabled()
    response = httpx.post(
        f"{config.jira_base_url}{path}",
        json=body,
        headers={**_headers(), "Content-Type": "application/json"},
        timeout=15,
    )
    response.raise_for_status()
    return response.json() if response.content else None


def my_open_issues() -> list[dict]:
    sprint_field = config.jira_sprint_field
    body = {
        "jql": "assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC",
        "fields": ["summary", "status", "priority", "updated", sprint_field],
        "maxResults": 100,
    }
    data = _post("/rest/api/3/search/jql", body) or {}
    return [_normalize(raw, sprint_field) for raw in data.get("issues", [])]


def _normalize(raw: dict, sprint_field: str) -> dict:
    fields = raw.get("fields", {}) or {}
    status = fields.get("status") or {}
    status_category = (status.get("statusCategory") or {}).get("key")
    priority = (fields.get("priority") or {}).get("name")
    sprints = fields.get(sprint_field) or []
    in_active_sprint = False
    for sprint in sprints:
        if isinstance(sprint, dict) and sprint.get("state") == "active":
            in_active_sprint = True
            break
    return {
        "key": raw["key"],
        "url": f"{config.jira_base_url}/browse/{raw['key']}",
        "summary": fields.get("summary"),
        "status": status.get("name"),
        "statusCategory": status_category,
        "priority": priority,
        "updated": fields.get("updated"),
        "inActiveSprint": in_active_sprint,
    }


def transitions(issue_key: str) -> list[dict]:
    data = _get(f"/rest/api/3/issue/{issue_key}/transitions")
    return [
        {
            "id": t["id"],
            "name": t["name"],
            "to": (t.get("to") or {}).get("name"),
        }
        for t in data.get("transitions", [])
    ]


def transition(issue_key: str, transition_id: str) -> None:
    _post(
        f"/rest/api/3/issue/{issue_key}/transitions",
        {"transition": {"id": transition_id}},
    )
