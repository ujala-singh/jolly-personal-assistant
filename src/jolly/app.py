"""Flask app: dashboard JSON, ticket transitions, Claude PR review jobs."""
from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from jolly.clients import jira, linear
from jolly.clients.linear import LinearError
from jolly.clients.jira import JiraError
from jolly.config import config
from jolly.services import claude_review, dashboard


def create_app() -> Flask:
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template("index.html", poll_seconds=config.poll_seconds)

    @app.route("/api/dashboard")
    def api_dashboard():
        return jsonify(dashboard.snapshot())

    @app.route("/api/tickets/<source>/<path:ticket_id>/transitions")
    def api_transitions(source: str, ticket_id: str):
        try:
            if source == "linear":
                team_id = request.args.get("teamId")
                if not team_id:
                    return jsonify({"error": "teamId query param required for linear"}), 400
                return jsonify({"transitions": linear.workflow_states(team_id)})
            if source == "jira":
                return jsonify({"transitions": jira.transitions(ticket_id)})
            return jsonify({"error": f"unknown source: {source}"}), 400
        except (LinearError, JiraError) as exc:
            return jsonify({"error": str(exc)}), 502

    @app.route("/api/tickets/<source>/<path:ticket_id>/transition", methods=["POST"])
    def api_transition(source: str, ticket_id: str):
        body = request.get_json(silent=True) or {}
        target = body.get("targetId")
        if not target:
            return jsonify({"error": "targetId required in body"}), 400
        try:
            if source == "linear":
                result = linear.transition(ticket_id, target)
                return jsonify({"success": bool(result.get("success")), "result": result})
            if source == "jira":
                jira.transition(ticket_id, target)
                return jsonify({"success": True})
            return jsonify({"error": f"unknown source: {source}"}), 400
        except (LinearError, JiraError) as exc:
            return jsonify({"error": str(exc)}), 502

    @app.route("/api/prs/<owner>/<repo>/<int:number>/review", methods=["POST"])
    def api_start_review(owner: str, repo: str, number: int):
        job_id = claude_review.start_review(f"{owner}/{repo}", number)
        return jsonify({"jobId": job_id})

    @app.route("/api/reviews/<job_id>")
    def api_get_review(job_id: str):
        job = claude_review.get_job(job_id)
        if not job:
            return jsonify({"error": "job not found"}), 404
        return jsonify(job)

    return app


def main() -> None:
    app = create_app()
    print(f"jolly running on http://127.0.0.1:{config.port}")
    app.run(host="127.0.0.1", port=config.port, debug=False)


if __name__ == "__main__":
    main()
