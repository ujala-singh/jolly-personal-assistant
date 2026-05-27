"""GitHub access via the local `gh` CLI — uses your existing auth, no PAT in env."""
from __future__ import annotations

import json
import subprocess
from typing import Any


class GhError(RuntimeError):
    pass


def _gh_json(*args: str) -> Any:
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise GhError("`gh` CLI not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise GhError(f"gh {' '.join(args)} failed: {exc.stderr.strip() or exc.stdout.strip()}") from exc
    out = result.stdout.strip()
    return json.loads(out) if out else None


def my_open_prs() -> list[dict]:
    base = "number,title,url,repository,updatedAt,isDraft"
    rows = _gh_json(
        "search", "prs",
        "--author", "@me",
        "--state", "open",
        "--json", base,
        "--limit", "50",
    ) or []
    return [_enrich_pr(row) for row in rows]


def review_requests() -> list[dict]:
    rows = _gh_json(
        "search", "prs",
        "--review-requested", "@me",
        "--state", "open",
        "--json", "number,title,url,repository,author,updatedAt,isDraft",
        "--limit", "50",
    ) or []
    return [{
        "number": row["number"],
        "title": row["title"],
        "url": row["url"],
        "repo": row["repository"]["nameWithOwner"],
        "author": (row.get("author") or {}).get("login"),
        "updatedAt": row["updatedAt"],
        "isDraft": row.get("isDraft", False),
    } for row in rows]


def _enrich_pr(row: dict) -> dict:
    repo = row["repository"]["nameWithOwner"]
    detail = _gh_json(
        "pr", "view", str(row["number"]),
        "--repo", repo,
        "--json", "statusCheckRollup,reviewDecision,mergeable,headRefName",
    ) or {}
    return {
        "number": row["number"],
        "title": row["title"],
        "url": row["url"],
        "repo": repo,
        "updatedAt": row["updatedAt"],
        "isDraft": row.get("isDraft", False),
        "headRef": detail.get("headRefName"),
        "mergeable": detail.get("mergeable"),
        "reviewDecision": detail.get("reviewDecision"),
        "checks": _summarize_checks(detail.get("statusCheckRollup") or []),
    }


def _summarize_checks(rollup: list[dict]) -> dict:
    total = len(rollup)
    failing = 0
    pending = 0
    for check in rollup:
        conclusion = check.get("conclusion")
        status = check.get("status")
        state = check.get("state")
        if conclusion in {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"} or state == "FAILURE" or state == "ERROR":
            failing += 1
        elif status in {"IN_PROGRESS", "QUEUED", "PENDING"} or state == "PENDING":
            pending += 1
    passing = total - failing - pending
    if total == 0:
        status_label = "none"
    elif failing:
        status_label = "failing"
    elif pending:
        status_label = "pending"
    else:
        status_label = "passing"
    return {
        "status": status_label,
        "total": total,
        "passing": passing,
        "failing": failing,
        "pending": pending,
    }


def pr_diff(repo: str, number: int) -> str:
    try:
        result = subprocess.run(
            ["gh", "pr", "diff", str(number), "--repo", repo],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
    except subprocess.CalledProcessError as exc:
        raise GhError(f"gh pr diff failed: {exc.stderr.strip() or exc.stdout.strip()}") from exc
    return result.stdout
