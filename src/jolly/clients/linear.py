"""Linear GraphQL client. Read assigned issues + transition workflow state."""
from __future__ import annotations

import httpx

from jolly.config import config

LINEAR_URL = "https://api.linear.app/graphql"


class LinearError(RuntimeError):
    pass


def _query(query: str, variables: dict | None = None) -> dict:
    if not config.linear_enabled:
        raise LinearError("LINEAR_API_KEY not set")
    response = httpx.post(
        LINEAR_URL,
        json={"query": query, "variables": variables or {}},
        headers={
            "Authorization": config.linear_api_key,
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise LinearError(f"Linear API errors: {payload['errors']}")
    return payload["data"]


MY_OPEN_ISSUES = """
query MyIssues {
  viewer {
    id
    assignedIssues(filter: { completedAt: { null: true } }, first: 100) {
      nodes {
        id identifier title url updatedAt
        priorityLabel
        state { id name type color }
        cycle { id name endsAt isActive }
        team { id key name }
      }
    }
  }
}
"""

WORKFLOW_STATES = """
query States($teamId: String!) {
  workflowStates(filter: { team: { id: { eq: $teamId } } }) {
    nodes { id name type }
  }
}
"""

TRANSITION = """
mutation Transition($id: String!, $stateId: String!) {
  issueUpdate(id: $id, input: { stateId: $stateId }) {
    success
    issue { id state { id name type } }
  }
}
"""


def my_open_issues() -> list[dict]:
    data = _query(MY_OPEN_ISSUES)
    nodes = data["viewer"]["assignedIssues"]["nodes"]
    return [n for n in nodes if n["state"]["type"] not in ("completed", "canceled")]


def workflow_states(team_id: str) -> list[dict]:
    nodes = _query(WORKFLOW_STATES, {"teamId": team_id})["workflowStates"]["nodes"]
    return [{"id": n["id"], "name": n["name"], "type": n["type"]} for n in nodes]


def transition(issue_id: str, state_id: str) -> dict:
    return _query(TRANSITION, {"id": issue_id, "stateId": state_id})["issueUpdate"]
