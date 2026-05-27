# Jolly's Personal Assistant

A personal command center, served locally. One page that shows:

- **Today** — tickets currently in progress or in your active Linear cycle / Jira sprint
- **This week** — Mon–Fri Google Calendar events
- **All assigned tickets** — every open Linear + Jira issue assigned to you, with one-click state transitions
- **My open PRs** — checks status, review decision, draft/conflict state, links
- **Review requests** — PRs waiting on your review
- **Review with claude** — a button on every PR that pipes the diff to `claude -p` and shows the response in a popup

Runs at `http://127.0.0.1:8765`. Auto-refreshes every 5 minutes.

## Setup

```bash
# 1. uv (https://docs.astral.sh/uv)
brew install uv

# 2. install deps
uv sync

# 3. ensure gh is authed — jolly uses it for all GitHub calls, no PAT needed
gh auth status || gh auth login

# 4. fill in tokens
cp .env.example .env
# edit:
#   JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN  → https://id.atlassian.com/manage-profile/security/api-tokens
#   LINEAR_API_KEY                              → Linear → Settings → API → Personal API keys
#   GCAL_ICS_URLS                               → see "Calendar" section below

# 5. run
uv run jolly
# open http://127.0.0.1:8765
```

## How review-with-claude works

1. Browser hits `POST /api/prs/<owner>/<repo>/<number>/review` and gets a `jobId`.
2. Flask spawns a background thread that runs `gh pr diff <number> --repo <owner>/<repo>` and pipes the diff into `claude -p "<review prompt>"` via stdin.
3. Browser polls `GET /api/reviews/<jobId>` every 2s; once status is `done`, the markdown response is rendered into the modal.

Requirements: `claude` and `gh` both on PATH, both signed in. Reviews typically take 15–60 seconds.

## Environment

| Var | Required | Default | Notes |
|---|---|---|---|
| `JIRA_BASE_URL` | for Jira | — | e.g. `https://yourorg.atlassian.net` |
| `JIRA_EMAIL` | for Jira | — | account email |
| `JIRA_API_TOKEN` | for Jira | — | Atlassian API token |
| `JIRA_SPRINT_FIELD` | optional | `customfield_10020` | override if your sprint field id differs |
| `LINEAR_API_KEY` | for Linear | — | personal API key |
| `GCAL_ICS_URLS` | for calendar | — | comma-separated private iCal URLs |
| `PORT` | optional | `8765` | |
| `POLL_SECONDS` | optional | `300` | browser auto-refresh interval |

Missing credentials for a source disables that source — the dashboard renders what it can and surfaces any source errors in the sync indicator.

## Calendar (Google Calendar via ICS feed)

No OAuth needed. For each calendar you want to see on the dashboard:

1. Open [Google Calendar](https://calendar.google.com) in a browser.
2. Click the gear icon → **Settings**.
3. In the left sidebar, under **Settings for my calendars**, click the calendar name.
4. Scroll to **Integrate calendar**.
5. Copy the **Secret address in iCal format** (it ends in `.ics`). Treat this like a password — anyone with the URL can read every event on the calendar.
6. Paste it into `.env` as `GCAL_ICS_URLS=...`.
7. For multiple calendars, comma-separate the URLs.

If `GCAL_ICS_URLS` is empty, the **this week** section shows setup instructions instead of failing. Recurring events (standups, weekly 1:1s) are expanded to their real instances in the current week.

## Project layout

```
src/jolly/
├── app.py                    # Flask routes
├── config.py                 # env loading
├── clients/
│   ├── github.py             # shells out to gh CLI
│   ├── linear.py             # GraphQL
│   ├── jira.py               # REST v3 (/search/jql + /transitions)
│   └── gcal.py               # fetches private ICS URLs, expands recurring events
├── services/
│   ├── dashboard.py          # parallel fetch + merge
│   └── claude_review.py      # async claude -p jobs (in-memory)
├── templates/index.html
└── static/
    ├── app.css
    └── app.js
```

## Notes

- Job state is in-memory. Restarting the server drops any in-flight reviews.
- `gh search prs --author=@me` is scoped to repos you can see — that's the same surface as github.com's "Your pull requests" page.
- Linear filtering excludes `completed` and `canceled` states. Jira uses `statusCategory != Done`.
- The HTML/CSS/JS is intentionally embedded with no build step — `uv run jolly` is enough.
