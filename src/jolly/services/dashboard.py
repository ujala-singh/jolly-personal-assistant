"""Fan-out fetch across GitHub, Linear, and Jira. Returns a single snapshot."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar

from jolly.clients import gcal, github, jira, linear
from jolly.config import config

T = TypeVar("T")

IN_PROGRESS_STATE_TYPES = {"started", "inprogress", "in-progress", "indeterminate"}


def snapshot() -> dict:
    with ThreadPoolExecutor(max_workers=5) as pool:
        gh_prs_fut = pool.submit(_safe, github.my_open_prs)
        gh_reviews_fut = pool.submit(_safe, github.review_requests)
        linear_fut = pool.submit(_safe, linear.my_open_issues) if config.linear_enabled else None
        jira_fut = pool.submit(_safe, jira.my_open_issues) if config.jira_enabled else None
        gcal_fut = pool.submit(_safe, gcal.week_schedule) if gcal.is_available() else None

    gh_prs, gh_prs_err = gh_prs_fut.result()
    gh_reviews, gh_reviews_err = gh_reviews_fut.result()
    linear_issues, linear_err = linear_fut.result() if linear_fut else ([], None)
    jira_issues, jira_err = jira_fut.result() if jira_fut else ([], None)
    events, gcal_err = gcal_fut.result() if gcal_fut else ([], None)

    linear_issues = linear_issues or []
    jira_issues = jira_issues or []

    tickets_all = _merge_tickets(linear_issues, jira_issues)
    return {
        "tickets": {
            "all": tickets_all,
            "daily": [t for t in tickets_all if _is_daily(t)],
        },
        "prs": {
            "mine": gh_prs or [],
            "reviewRequests": gh_reviews or [],
        },
        "calendar": {
            "enabled": gcal.is_available(),
            "days": gcal.week_dates(),
            "events": events or [],
        },
        "sources": {
            "linear": config.linear_enabled,
            "jira": config.jira_enabled,
            "gcal": gcal.is_available(),
        },
        "errors": _collect_errors({
            "github_prs": gh_prs_err,
            "github_reviews": gh_reviews_err,
            "linear": linear_err if config.linear_enabled else None,
            "jira": jira_err if config.jira_enabled else None,
            "gcal": gcal_err if gcal.is_available() else None,
        }),
    }


def _is_daily(ticket: dict) -> bool:
    if ticket.get("inActiveCycle"):
        return True
    state_type = (ticket.get("stateType") or "").lower()
    return state_type in IN_PROGRESS_STATE_TYPES


def _safe(fn: Callable[[], T]) -> tuple[T | None, str | None]:
    try:
        return fn(), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def _collect_errors(raw: dict[str, str | None]) -> dict[str, str]:
    return {k: v for k, v in raw.items() if v}


def _merge_tickets(linear_issues: list[dict], jira_issues: list[dict]) -> list[dict]:
    tickets: list[dict] = []
    for issue in linear_issues:
        cycle = issue.get("cycle") or {}
        team = issue.get("team") or {}
        tickets.append({
            "source": "linear",
            "id": issue["id"],
            "key": issue["identifier"],
            "title": issue["title"],
            "url": issue["url"],
            "state": issue["state"]["name"],
            "stateType": issue["state"]["type"],
            "priority": issue.get("priorityLabel") or None,
            "cycle": cycle.get("name"),
            "inActiveCycle": bool(cycle.get("isActive")),
            "team": team.get("id"),
            "teamKey": team.get("key"),
            "updated": issue["updatedAt"],
        })
    for issue in jira_issues:
        tickets.append({
            "source": "jira",
            "id": issue["key"],
            "key": issue["key"],
            "title": issue["summary"],
            "url": issue["url"],
            "state": issue["status"],
            "stateType": issue.get("statusCategory"),
            "priority": issue.get("priority"),
            "cycle": None,
            "inActiveCycle": issue.get("inActiveSprint", False),
            "team": None,
            "teamKey": None,
            "updated": issue.get("updated"),
        })
    tickets.sort(key=lambda t: t.get("updated") or "", reverse=True)
    return tickets
