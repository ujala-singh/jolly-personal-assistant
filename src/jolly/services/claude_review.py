"""Async PR review jobs. Shells out to `gh pr diff | claude -p`."""
from __future__ import annotations

import subprocess
import threading
import uuid
from datetime import datetime, timezone
from typing import Literal

from jolly.clients import github

JobStatus = Literal["pending", "running", "done", "error"]

_jobs: dict[str, dict] = {}
_lock = threading.Lock()

REVIEW_PROMPT = (
    "Review this pull request diff. Output GitHub-flavored markdown with these sections:\n"
    "\n"
    "1. **TL;DR** — one line: ship / changes needed / blocker.\n"
    "2. **What it does** — 2-3 bullets.\n"
    "3. **Findings** — numbered, grouped by severity (critical / high / medium / low). "
    "Skip the section entirely if there are no findings at that severity.\n"
    "4. **Suggestions** — optional polish items. Skip if none.\n"
    "\n"
    "Be terse. Reference file paths and line snippets where useful. Prefer concrete fixes over vague advice.\n"
)


def start_review(repo: str, number: int) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "repo": repo,
            "number": number,
            "status": "pending",
            "createdAt": _now(),
            "finishedAt": None,
            "result": None,
            "error": None,
        }
    thread = threading.Thread(target=_run, args=(job_id, repo, number), daemon=True)
    thread.start()
    return job_id


def get_job(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def _set(job_id: str, **fields) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(job_id: str, repo: str, number: int) -> None:
    _set(job_id, status="running")
    try:
        diff = github.pr_diff(repo, number)
        if not diff.strip():
            raise RuntimeError("empty diff returned by gh")
        result = subprocess.run(
            ["claude", "-p", REVIEW_PROMPT],
            input=diff,
            capture_output=True,
            text=True,
            check=True,
            timeout=240,
        )
        _set(
            job_id,
            status="done",
            result=result.stdout.strip(),
            finishedAt=_now(),
        )
    except FileNotFoundError:
        _set(job_id, status="error", error="`claude` CLI not found on PATH", finishedAt=_now())
    except subprocess.TimeoutExpired:
        _set(job_id, status="error", error="claude timed out after 4 minutes", finishedAt=_now())
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "claude exited non-zero").strip()
        _set(job_id, status="error", error=message, finishedAt=_now())
    except Exception as exc:  # noqa: BLE001
        _set(job_id, status="error", error=f"{type(exc).__name__}: {exc}", finishedAt=_now())
