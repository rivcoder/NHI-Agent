"""
pubsub_handler.py — Cloud Run service for NHI Governance Agent

Endpoints:
  POST /scan   — triggered by Cloud Scheduler every hour
                 runs scanner + saves to MongoDB + publishes alerts
  POST /alert  — Pub/Sub push endpoint
                 receives CRITICAL alert and logs / notifies
  GET  /health — health check

Deploy: gcloud run deploy nhi-alert-handler --source=. ...
"""

import os
import json
import base64
import logging
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("nhi-agent")

app = Flask(__name__)


@app.route("/scan", methods=["POST"])
def trigger_scan():
    """
    Called by Cloud Scheduler every hour.
    Body: {"repo": "https://gitlab.com/org/repo"}
    """
    try:
        body         = request.get_json(force=True) or {}
        repo_url     = body.get("repo") or os.getenv("GITLAB_REPO", "demo")
        gitlab_token = os.getenv("GITLAB_TOKEN")

        log.info(f"[scan] Starting scan for {repo_url}")

        from scanner import scan_gitlab_repo, score_risk_with_gemini
        raw    = scan_gitlab_repo(repo_url, gitlab_token)
        scored = score_risk_with_gemini(raw)

        log.info(f"[scan] Found {len(scored)} NHIs")

        # Persist to MongoDB
        try:
            from db import save_scan, get_drift_summary
            scan_id = save_scan(repo_url, scored)
            log.info(f"[scan] Saved scan {scan_id}")

            drifts = get_drift_summary(repo=repo_url)
            if drifts:
                log.warning(f"[scan] Drift detected: {drifts}")
        except Exception as e:
            log.error(f"[scan] MongoDB error: {e}")

        # Publish alerts for CRITICAL findings
        critical = [r for r in scored if r.get("risk") == "CRITICAL"]
        if critical:
            _publish_critical_alert(repo_url, critical)

        return jsonify({
            "status":   "ok",
            "repo":     repo_url,
            "total":    len(scored),
            "critical": len(critical),
        }), 200

    except Exception as e:
        log.exception(f"[scan] Unhandled error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/alert", methods=["POST"])
def receive_alert():
    """
    Pub/Sub push endpoint.
    Receives CRITICAL alert message, logs it, optionally notifies Slack/email.
    """
    try:
        envelope = request.get_json(force=True)
        if not envelope or "message" not in envelope:
            return "Bad request", 400

        data    = base64.b64decode(envelope["message"]["data"]).decode("utf-8")
        payload = json.loads(data)

        repo     = payload.get("repo", "unknown")
        findings = payload.get("critical_findings", [])

        log.critical(f"[alert] CRITICAL NHIs detected in {repo}: {len(findings)} finding(s)")
        for f in findings:
            log.critical(f"  → {f.get('file')}:{f.get('line')} [{f.get('pattern')}]")

        # post to slack if webhook is set
        slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
        if slack_webhook:
            _notify_slack(slack_webhook, repo, findings)

        return "OK", 200

    except Exception as e:
        log.exception(f"[alert] Error processing Pub/Sub message: {e}")
        return "Error", 500


@app.route("/tools/scan", methods=["POST"])
def tool_scan():
    """
    scan_repo tool endpoint.
    Body: {"repo_url": "...", "gitlab_token": "..."} (optional token)
    """
    try:
        body = request.get_json(force=True) or {}
        repo_url = body.get("repo_url")
        if not repo_url:
            return jsonify({"status": "error", "message": "repo_url is required"}), 400
        
        gitlab_token = body.get("gitlab_token") or os.getenv("GITLAB_TOKEN")
        
        from scanner import scan_gitlab_repo
        raw = scan_gitlab_repo(repo_url, gitlab_token)
        return jsonify({"findings": raw}), 200
    except Exception as e:
        log.exception(f"[tool_scan] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/tools/score", methods=["POST"])
def tool_score():
    """
    score_findings tool endpoint.
    Body: {"findings": [...]}
    """
    try:
        body = request.get_json(force=True) or {}
        findings = body.get("findings")
        if findings is None:
            return jsonify({"status": "error", "message": "findings list is required"}), 400
        
        from scanner import score_risk_with_gemini
        scored = score_risk_with_gemini(findings)
        return jsonify({"scored_findings": scored}), 200
    except Exception as e:
        log.exception(f"[tool_score] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/tools/save", methods=["POST"])
def tool_save():
    """
    save_to_mongodb tool endpoint.
    Body: {"repo_url": "...", "scored_findings": [...]}
    """
    try:
        body = request.get_json(force=True) or {}
        repo_url = body.get("repo_url")
        findings = body.get("scored_findings")
        if not repo_url or findings is None:
            return jsonify({"status": "error", "message": "repo_url and scored_findings are required"}), 400
        
        from db import save_scan
        scan_id = save_scan(repo_url, findings)
        return jsonify({"status": "ok", "scan_id": scan_id}), 200
    except Exception as e:
        log.exception(f"[tool_save] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/tools/drift", methods=["POST"])
def tool_drift():
    """
    check_drift tool endpoint.
    Body: {"repo_url": "..."}
    """
    try:
        body = request.get_json(force=True) or {}
        repo_url = body.get("repo_url")
        if not repo_url:
            return jsonify({"status": "error", "message": "repo_url is required"}), 400
        
        from db import get_drift_summary
        drifts = get_drift_summary(repo=repo_url)
        return jsonify({"drifts": drifts}), 200
    except Exception as e:
        log.exception(f"[tool_drift] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/tools/publish", methods=["POST"])
def tool_publish():
    """
    publish_alert tool endpoint.
    Body: {"repo_url": "...", "critical_findings": [...]}
    """
    try:
        body = request.get_json(force=True) or {}
        repo_url = body.get("repo_url")
        findings = body.get("critical_findings")
        if not repo_url or not findings:
            return jsonify({"status": "error", "message": "repo_url and critical_findings are required"}), 400
        
        _publish_critical_alert(repo_url, findings)
        return jsonify({"status": "ok", "message": "Alert published successfully"}), 200
    except Exception as e:
        log.exception(f"[tool_publish] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


def _publish_critical_alert(repo: str, critical_findings: list):
    """Publish a message to the Pub/Sub CRITICAL alerts topic."""
    try:
        from google.cloud import pubsub_v1
        project_id  = os.getenv("GCP_PROJECT_ID")
        topic_id    = os.getenv("PUBSUB_TOPIC", "nhi-critical-alerts")
        publisher   = pubsub_v1.PublisherClient()
        topic_path  = publisher.topic_path(project_id, topic_id)

        payload = json.dumps({
            "repo": repo,
            "critical_findings": [
                {
                    "file":    r.get("raw", {}).get("file") if isinstance(r.get("raw"), dict) else r.get("file", ""),
                    "line":    r.get("raw", {}).get("line") if isinstance(r.get("raw"), dict) else r.get("line", 0),
                    "pattern": r.get("raw", {}).get("pattern") if isinstance(r.get("raw"), dict) else r.get("pattern", ""),
                    "action":  r.get("action", ""),
                }
                for r in critical_findings
            ]
        }).encode("utf-8")

        future = publisher.publish(topic_path, payload)
        msg_id = future.result()
        log.info(f"[alert] Published CRITICAL alert to {topic_id}, message_id={msg_id}")

    except Exception as e:
        log.error(f"[alert] Pub/Sub publish failed: {e}")


def _notify_slack(webhook_url: str, repo: str, findings: list):
    import requests
    lines = "\n".join(f"• `{f['file']}:{f['line']}` — `{f['pattern']}`" for f in findings)
    msg = {
        "text": f"🔴 *CRITICAL NHIs detected* in `{repo}`\n{lines}\n\nCheck the dashboard immediately."
    }
    try:
        requests.post(webhook_url, json=msg, timeout=5)
    except Exception as e:
        log.error(f"[alert] Slack notify failed: {e}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
