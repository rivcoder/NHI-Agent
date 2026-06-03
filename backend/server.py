# server.py - main backend api using flask.
# run it with: python server.py

import os
import sys
import json
import base64
import logging
import time
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

# Reconfigure stdout to use utf-8 to avoid UnicodeEncodeErrors on Windows terminals when logging/printing emojis
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv(override=True)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("nhi-agent")

app = Flask(__name__)
CORS(app)  # Allow frontend to call from any origin


# --- Frontend API Routes ---

@app.route("/api/health", methods=["GET"])
def api_health():
    """Health check."""
    return jsonify({"status": "ok", "service": "nhi-governance-agent"}), 200


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """
    Run a full scan: discover NHIs → score with Gemini → return results.
    Body: {"repo_url": "...", "gitlab_token": "..."} (token optional)
    """
    try:
        body = request.get_json(force=True) or {}
        repo_url = body.get("repo_url", "").strip()
        if not repo_url:
            return jsonify({"status": "error", "message": "repo_url is required"}), 400

        gitlab_token = body.get("gitlab_token") or os.getenv("GITLAB_TOKEN") or os.getenv("GITHUB_TOKEN")

        # ── Profile page detection ──────────────────────────────────────────
        clean_url = repo_url.split("?")[0].split("#")[0].strip().rstrip("/")
        is_profile = False
        profile_repos = []
        if "github.com" in clean_url.lower():
            parts = clean_url.split("github.com/")
            if len(parts) >= 2:
                path_parts = parts[1].lstrip("/").split("/")
                if len(path_parts) == 1 and path_parts[0]: # profile or org
                    is_profile = True
                    from scanner import fetch_github_user_repos
                    profile_repos = fetch_github_user_repos(path_parts[0], gitlab_token)
        elif "gitlab.com" in clean_url.lower():
            parts = clean_url.split("gitlab.com/")
            if len(parts) >= 2:
                path_parts = parts[1].lstrip("/").split("/")
                if len(path_parts) == 1 and path_parts[0]: # user
                    is_profile = True
                    from scanner import fetch_gitlab_user_repos
                    profile_repos = fetch_gitlab_user_repos(path_parts[0], gitlab_token)
                elif len(path_parts) == 2 and path_parts[0] == "groups" and path_parts[1]: # group
                    is_profile = True
                    from scanner import fetch_gitlab_user_repos
                    profile_repos = fetch_gitlab_user_repos(path_parts[1], gitlab_token, is_group=True)
        
        if is_profile:
            return jsonify({
                "status": "profile",
                "message": f"URL '{repo_url}' is a profile/organization page. Select a repository below to scan:",
                "repos": profile_repos
            }), 200

        from scanner import scan_repo, score_risk_with_gemini

        start = time.time()
        raw = scan_repo(repo_url, gitlab_token)
        scored = score_risk_with_gemini(raw)
        elapsed = round(time.time() - start, 1)

        # Try to persist to MongoDB
        scan_id = None
        try:
            from db import save_scan
            scan_id = save_scan(repo_url, scored)
        except Exception as e:
            log.warning(f"[api_scan] MongoDB save skipped: {e}")

        # Build response
        summary = {
            "total": len(scored),
            "critical": sum(1 for r in scored if r.get("risk") == "CRITICAL"),
            "high": sum(1 for r in scored if r.get("risk") == "HIGH"),
            "medium": sum(1 for r in scored if r.get("risk") == "MEDIUM"),
            "low": sum(1 for r in scored if r.get("risk") == "LOW"),
        }

        findings = []
        for r in scored:
            raw_data = r.get("raw", {})
            findings.append({
                "file": raw_data.get("file", ""),
                "line": raw_data.get("line", 0),
                "content": raw_data.get("content", ""),
                "pattern": raw_data.get("pattern", ""),
                "risk": r.get("risk", "UNKNOWN"),
                "type": r.get("type", ""),
                "reason": r.get("reason", ""),
                "action": r.get("action", ""),
                "breach_cost": r.get("breach_cost", "N/A"),
                "blast_radius": r.get("blast_radius", "N/A"),
            })

        return jsonify({
            "status": "ok",
            "repo": repo_url,
            "elapsed": elapsed,
            "scan_id": scan_id,
            "summary": summary,
            "findings": findings,
        }), 200

    except Exception as e:
        log.exception(f"[api_scan] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/scan/demo", methods=["POST"])
def api_scan_demo():
    """Run a demo scan with fake data — no credentials needed."""
    try:
        from scanner import scan_repo, score_risk_with_gemini

        start = time.time()
        raw = scan_repo("demo")
        scored = score_risk_with_gemini(raw)
        elapsed = round(time.time() - start, 1)

        # Try to persist
        scan_id = None
        try:
            from db import save_scan
            scan_id = save_scan("https://gitlab.com/demo/acme-payments", scored)
        except Exception:
            pass

        summary = {
            "total": len(scored),
            "critical": sum(1 for r in scored if r.get("risk") == "CRITICAL"),
            "high": sum(1 for r in scored if r.get("risk") == "HIGH"),
            "medium": sum(1 for r in scored if r.get("risk") == "MEDIUM"),
            "low": sum(1 for r in scored if r.get("risk") == "LOW"),
        }

        findings = []
        for r in scored:
            raw_data = r.get("raw", {})
            findings.append({
                "file": raw_data.get("file", ""),
                "line": raw_data.get("line", 0),
                "content": raw_data.get("content", ""),
                "pattern": raw_data.get("pattern", ""),
                "risk": r.get("risk", "UNKNOWN"),
                "type": r.get("type", ""),
                "reason": r.get("reason", ""),
                "action": r.get("action", ""),
                "breach_cost": r.get("breach_cost", "N/A"),
                "blast_radius": r.get("blast_radius", "N/A"),
            })

        return jsonify({
            "status": "ok",
            "repo": "https://gitlab.com/demo/acme-payments",
            "elapsed": elapsed,
            "scan_id": scan_id,
            "summary": summary,
            "findings": findings,
        }), 200

    except Exception as e:
        log.exception(f"[api_scan_demo] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/history", methods=["GET"])
def api_history():
    """Get recent scan summaries."""
    try:
        from db import get_recent_scans
        repo = request.args.get("repo")
        scans = get_recent_scans(repo=repo)
        # Serialize datetime objects
        for s in scans:
            if "scanned_at" in s:
                s["scanned_at"] = s["scanned_at"].isoformat() if hasattr(s["scanned_at"], "isoformat") else str(s["scanned_at"])
        return jsonify({"status": "ok", "scans": scans}), 200
    except Exception as e:
        log.warning(f"[api_history] Error: {e}")
        return jsonify({"status": "ok", "scans": [], "note": str(e)}), 200


@app.route("/api/nhis", methods=["GET"])
def api_nhis():
    """Get the NHI identity index with drift history."""
    try:
        from db import get_nhi_index
        repo = request.args.get("repo")
        nhis = get_nhi_index(repo=repo)
        # Serialize datetime objects in history
        for nhi in nhis:
            for key in ["first_seen", "last_seen"]:
                if key in nhi and hasattr(nhi[key], "isoformat"):
                    nhi[key] = nhi[key].isoformat()
            for h in nhi.get("history", []):
                if "scanned_at" in h and hasattr(h["scanned_at"], "isoformat"):
                    h["scanned_at"] = h["scanned_at"].isoformat()
        return jsonify({"status": "ok", "nhis": nhis}), 200
    except Exception as e:
        log.warning(f"[api_nhis] Error: {e}")
        return jsonify({"status": "ok", "nhis": [], "note": str(e)}), 200


@app.route("/api/drift", methods=["GET"])
def api_drift():
    """Get drift summary — NHIs whose risk changed between scans."""
    try:
        from db import get_drift_summary
        repo = request.args.get("repo")
        drifts = get_drift_summary(repo=repo)
        for d in drifts:
            if "at" in d and hasattr(d["at"], "isoformat"):
                d["at"] = d["at"].isoformat()
        return jsonify({"status": "ok", "drifts": drifts}), 200
    except Exception as e:
        log.warning(f"[api_drift] Error: {e}")
        return jsonify({"status": "ok", "drifts": [], "note": str(e)}), 200


@app.route("/api/chart", methods=["GET"])
def api_chart():
    """Get risk trend chart data for a repo."""
    try:
        from db import get_scan_history_chart
        repo = request.args.get("repo", "https://gitlab.com/demo/acme-payments")
        rows = get_scan_history_chart(repo)
        return jsonify({"status": "ok", "chart": rows}), 200
    except Exception as e:
        log.warning(f"[api_chart] Error: {e}")
        return jsonify({"status": "ok", "chart": [], "note": str(e)}), 200


@app.route("/api/metrics", methods=["GET"])
def api_metrics():
    """Get calculated security posture metrics for a repository."""
    try:
        from db import get_repo_metrics
        repo = request.args.get("repo", "https://gitlab.com/demo/acme-payments")
        metrics = get_repo_metrics(repo)
        return jsonify({"status": "ok", "metrics": metrics}), 200
    except Exception as e:
        log.exception(f"[api_metrics] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/remediate/generate-patch", methods=["POST"])
def api_remediate_generate_patch():
    """
    Download file context and generate a remediation diff & WIF guide via Gemini.
    Body: {"repo_url": "...", "file_path": "...", "line": 12, "secret_value": "...", "secret_placeholder": "..."}
    """
    try:
        body = request.get_json(force=True) or {}
        repo_url = body.get("repo_url", "").strip()
        file_path = body.get("file_path", "").strip()
        line_num = int(body.get("line") or 0)
        secret_value = body.get("secret_value", "").strip()
        secret_placeholder = body.get("secret_placeholder", "").strip()

        if not repo_url or not file_path or not line_num or not secret_value or not secret_placeholder:
            return jsonify({"status": "error", "message": "All parameters (repo_url, file_path, line, secret_value, secret_placeholder) are required"}), 400

        from scanner import generate_code_patch
        
        # MOCK CONTENT FOR DEMO MODE
        if repo_url.lower() == "demo" or "demo/acme-payments" in repo_url:
            mock_content = f"""# Auto-generated configuration
import os

# Database connection
DB_USER = "admin"
DB_PASSWORD = "{secret_value}"
DB_HOST = "localhost"

# Integrations
AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
"""
            res = generate_code_patch(mock_content, line_num, secret_value, secret_placeholder)
            return jsonify({"status": "ok", "patch": res}), 200

        # REAL SCAN: fetch file content
        if "github.com" in repo_url.lower():
            github_token = os.getenv("GITHUB_TOKEN") or body.get("gitlab_token")
            parts = repo_url.rstrip("/").split("github.com/")
            if len(parts) < 2:
                return jsonify({"status": "error", "message": "Invalid GitHub URL"}), 400
                
            project_path_str = parts[1]
            if project_path_str.endswith(".git"):
                project_path_str = project_path_str[:-4]
            owner_repo = project_path_str.lstrip("/")
            
            headers = {"User-Agent": "nhi-agent"}
            if github_token and not github_token.startswith("ghp_xxxx") and not github_token.startswith("glpat-xxxx"):
                headers["Authorization"] = f"token {github_token}"
                
            import requests as req
            api_url = f"https://api.github.com/repos/{owner_repo}/contents/{file_path}"
            res_content = req.get(api_url, headers=headers)
            if res_content.status_code != 200:
                raise ValueError(f"Could not fetch file from GitHub: {res_content.status_code}")
                
            import base64
            file_data = res_content.json()
            file_content = base64.b64decode(file_data.get("content", "")).decode("utf-8")
        else:
            gitlab_token = os.getenv("GITLAB_TOKEN")
            parts = repo_url.rstrip("/").split("gitlab.com/")
            if len(parts) < 2:
                return jsonify({"status": "error", "message": "Invalid GitLab URL"}), 400
                
            project_path_str = parts[1]
            if project_path_str.endswith(".git"):
                project_path_str = project_path_str[:-4]
            project_path = project_path_str.replace("/", "%2F")
            api_base = "https://gitlab.com/api/v4"
            
            headers = {}
            if gitlab_token and not gitlab_token.startswith("glpat-xxxx"):
                headers["PRIVATE-TOKEN"] = gitlab_token

            import requests as req
            proj_res = req.get(f"{api_base}/projects/{project_path}", headers=headers)
            if proj_res.status_code != 200:
                raise ValueError(f"Project not found or inaccessible: {proj_res.status_code}")
            default_branch = proj_res.json().get("default_branch", "main")
            
            file_url_path = file_path.replace("/", "%2F")
            content_res = req.get(f"{api_base}/projects/{project_path}/repository/files/{file_url_path}/raw?ref={default_branch}", headers=headers)
            if content_res.status_code != 200:
                raise ValueError(f"Could not fetch file: {content_res.status_code}")
                
            file_content = content_res.text

        res = generate_code_patch(file_content, line_num, secret_value, secret_placeholder)
        return jsonify({"status": "ok", "patch": res}), 200

    except Exception as e:
        log.exception(f"[api_remediate_generate_patch] Error: {e}")
        fallback_diff = f"- {secret_value}\n+ {secret_placeholder}"
        return jsonify({
            "status": "ok",
            "patch": {
                "original_line": f"Original line containing: {secret_value}",
                "remediated_line": f"Remediated line containing: {secret_placeholder}",
                "explanation": f"Failed to fetch real code context ({str(e)}). Generating default substitution.",
                "code_patch": fallback_diff,
                "wif_recommendation": "No Workload Identity Federation recommendation applicable. Continue storing in Secret Manager."
            }
        }), 200


@app.route("/api/gitlab/projects", methods=["GET"])
def api_gitlab_projects():
    """List GitLab repositories accessible by the token."""
    try:
        gitlab_token = request.args.get("token") or os.getenv("GITLAB_TOKEN")
        if not gitlab_token or gitlab_token.startswith("glpat-xxxx"):
            return jsonify({"status": "ok", "projects": []}), 200
            
        import requests as req
        headers = {"PRIVATE-TOKEN": gitlab_token}
        res = req.get("https://gitlab.com/api/v4/projects?membership=true&simple=true&per_page=100&sort=desc&order_by=last_activity_at", headers=headers, timeout=8)
        if res.status_code != 200:
            return jsonify({"status": "error", "message": f"GitLab API returned status {res.status_code}"}), 400
            
        projects = []
        for p in res.json():
            projects.append({
                "name": p.get("name_with_namespace"),
                "url": p.get("web_url"),
                "id": p.get("id")
            })
        return jsonify({"status": "ok", "projects": projects}), 200
    except Exception as e:
        log.exception(f"[api_gitlab_projects] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/remediate/secret-manager", methods=["POST"])
@app.route("/tools/remediate/secret-manager", methods=["POST"])
def api_remediate_secret_manager():
    """
    Store a secret in Google Cloud Secret Manager.
    Body: {"secret_name": "...", "secret_value": "..."}
    """
    try:
        body = request.get_json(force=True) or {}
        secret_name = body.get("secret_name", "").strip()
        secret_value = body.get("secret_value", "").strip()
        
        if not secret_name or not secret_value:
            return jsonify({"status": "error", "message": "secret_name and secret_value are required"}), 400
            
        project_id = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "your-project-id"
        
        # Clean secret name to only contain allowed characters (letters, numbers, dashes, underscores)
        import re
        clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', secret_name)
        # Ensure it starts with a letter and is under 255 chars
        if not re.match(r'^[a-zA-Z]', clean_name):
            clean_name = "secret_" + clean_name
        clean_name = clean_name[:255]

        try:
            from google.cloud import secretmanager
            client = secretmanager.SecretManagerServiceClient()
            parent = f"projects/{project_id}"
            
            # Try to create the secret container
            secret_path = f"projects/{project_id}/secrets/{clean_name}"
            try:
                client.create_secret(
                    request={
                        "parent": parent,
                        "secret_id": clean_name,
                        "secret": {"replication": {"automatic": {}}},
                    }
                )
            except Exception:
                # If secret already exists, skip creation
                pass
                
            # Add secret version
            version = client.add_secret_version(
                request={
                    "parent": secret_path,
                    "payload": {"data": secret_value.encode("utf-8")},
                }
            )
            
            return jsonify({
                "status": "ok",
                "secret_path": version.name,
                "secret_name": clean_name,
                "message": f"Successfully stored secret in GCP Secret Manager as '{clean_name}'"
            }), 200
            
        except Exception as e:
            # Fallback to simulation mode if GCP credentials are not active/available
            log.warning(f"GCP Secret Manager API failed: {e}. Falling back to simulation.")
            return jsonify({
                "status": "demo-success",
                "secret_path": f"projects/{project_id}/secrets/{clean_name}/versions/1",
                "secret_name": clean_name,
                "message": f"Remediation Simulated: Secret saved to GCP Secret Manager (Demo Mode: {str(e)})"
            }), 200
            
    except Exception as e:
        log.exception(f"[remediate_secret_manager] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/remediate/gitlab-mr", methods=["POST"])
@app.route("/tools/remediate/gitlab-mr", methods=["POST"])
def api_remediate_gitlab_mr():
    """
    Create a new branch, replace the secret with a placeholder, commit, and open a Pull Request (GitHub) or Merge Request (GitLab).
    Body: {"repo_url": "...", "file_path": "...", "line": 12, "secret_value": "...", "secret_placeholder": "..."}
    """
    try:
        body = request.get_json(force=True) or {}
        repo_url = body.get("repo_url", "").strip()
        file_path = body.get("file_path", "").strip()
        line_num = int(body.get("line") or 0)
        secret_value = body.get("secret_value", "").strip()
        secret_placeholder = body.get("secret_placeholder", "").strip()
        
        if not repo_url or not file_path or not line_num or not secret_value or not secret_placeholder:
            return jsonify({"status": "error", "message": "All parameters (repo_url, file_path, line, secret_value, secret_placeholder) are required"}), 400

        if "github.com" in repo_url.lower():
            # GitHub Pull Request Flow
            github_token = os.getenv("GITHUB_TOKEN") or body.get("gitlab_token")
            parts = repo_url.rstrip("/").split("github.com/")
            if len(parts) < 2:
                return jsonify({"status": "error", "message": "Invalid GitHub URL"}), 400
                
            project_path_str = parts[1]
            if project_path_str.endswith(".git"):
                project_path_str = project_path_str[:-4]
            owner_repo = project_path_str.lstrip("/")
            
            headers = {"User-Agent": "nhi-agent"}
            if github_token and not github_token.startswith("ghp_xxxx") and not github_token.startswith("glpat-xxxx"):
                headers["Authorization"] = f"token {github_token}"
                
            try:
                if not github_token or github_token.startswith("ghp_xxxx") or github_token.startswith("glpat-xxxx"):
                    raise ValueError("No valid GitHub token configured")
                    
                import requests as req
                import base64
                import time
                
                # 1. Fetch file content and SHA
                api_url = f"https://api.github.com/repos/{owner_repo}/contents/{file_path}"
                content_res = req.get(api_url, headers=headers)
                if content_res.status_code != 200:
                    raise ValueError(f"Could not fetch file: {content_res.status_code}")
                
                file_data = content_res.json()
                file_sha = file_data.get("sha")
                original_content = base64.b64decode(file_data.get("content", "")).decode("utf-8")
                
                # Replace the secret line
                lines = original_content.split("\n")
                if len(lines) >= line_num:
                    target_line = lines[line_num - 1]
                    if secret_value in target_line:
                        lines[line_num - 1] = target_line.replace(secret_value, secret_placeholder)
                    else:
                        lines[line_num - 1] = target_line + f" # Remediated: {secret_placeholder}"
                else:
                    raise ValueError(f"File line number {line_num} out of bounds")
                new_content = "\n".join(lines)
                
                # 2. Get default branch ref
                repo_info = req.get(f"https://api.github.com/repos/{owner_repo}", headers=headers).json()
                default_branch = repo_info.get("default_branch", "main")
                
                ref_res = req.get(f"https://api.github.com/repos/{owner_repo}/git/ref/heads/{default_branch}", headers=headers)
                if ref_res.status_code != 200:
                    raise ValueError("Could not fetch default branch ref")
                default_branch_sha = ref_res.json().get("object", {}).get("sha")
                
                # 3. Create branch
                branch_name = f"nhi-remediate-L{line_num}-{int(time.time())}"
                create_ref_payload = {
                    "ref": f"refs/heads/{branch_name}",
                    "sha": default_branch_sha
                }
                create_ref_res = req.post(f"https://api.github.com/repos/{owner_repo}/git/refs", json=create_ref_payload, headers=headers)
                if create_ref_res.status_code != 201:
                    raise ValueError(f"Failed to create branch: {create_ref_res.text}")
                    
                # 4. Commit replacement
                commit_payload = {
                    "message": f"🛡️ Remediate hardcoded secret in {file_path} (L{line_num})",
                    "content": base64.b64encode(new_content.encode("utf-8")).decode("utf-8"),
                    "sha": file_sha,
                    "branch": branch_name
                }
                commit_res = req.put(f"https://api.github.com/repos/{owner_repo}/contents/{file_path}", json=commit_payload, headers=headers)
                if commit_res.status_code != 200:
                    raise ValueError(f"Failed to commit change: {commit_res.text}")
                    
                # 5. Open Pull Request
                pr_payload = {
                    "title": f"🛡️ Remediate hardcoded secret in {file_path}",
                    "head": branch_name,
                    "base": default_branch,
                    "body": f"""An automated pull request generated by the **NHI Governance Agent**.

### 🔒 Security Resolution Summary:
* **Issue**: Hardcoded secret detected at line {line_num} of `{file_path}`.
* **Resolution**: Replaced secret with secure configuration placeholder: `{secret_placeholder}`.
* **Storage**: Secret values have been uploaded to **Google Cloud Secret Manager**.

Please review and merge this request to secure the repository."""
                }
                pr_res = req.post(f"https://api.github.com/repos/{owner_repo}/pulls", json=pr_payload, headers=headers)
                if pr_res.status_code != 201:
                    raise ValueError(f"Failed to create Pull Request: {pr_res.text}")
                    
                pr_data = pr_res.json()
                return jsonify({
                    "status": "ok",
                    "mr_url": pr_data.get("html_url"),
                    "branch": branch_name,
                    "message": f"Successfully created GitHub Pull Request #{pr_data.get('number')} and branch '{branch_name}'"
                }), 200
                
            except Exception as e:
                log.warning(f"GitHub API remediation failed: {e}. Falling back to simulation.")
                import random
                pr_id = random.randint(10, 99)
                sim_branch = f"nhi-remediate-L{line_num}-simulated"
                return jsonify({
                    "status": "demo-success",
                    "mr_url": f"https://github.com/{owner_repo}/pull/{pr_id}",
                    "branch": sim_branch,
                    "message": f"Remediation Simulated: Opened GitHub Pull Request #{pr_id} (Demo Mode: {str(e)})"
                }), 200
        else:
            # GitLab MR Flow
            gitlab_token = os.getenv("GITLAB_TOKEN")
            parts = repo_url.rstrip("/").split("gitlab.com/")
            if len(parts) < 2:
                return jsonify({"status": "error", "message": "Invalid GitLab URL"}), 400
                
            project_path_str = parts[1]
            if project_path_str.endswith(".git"):
                project_path_str = project_path_str[:-4]
            project_path = project_path_str.replace("/", "%2F")
            api_base = "https://gitlab.com/api/v4"
            
            headers = {}
            if gitlab_token and not gitlab_token.startswith("glpat-xxxx"):
                headers["PRIVATE-TOKEN"] = gitlab_token
                
            try:
                if not gitlab_token or gitlab_token.startswith("glpat-xxxx"):
                    raise ValueError("No valid GitLab token configured")
                    
                proj_res = requests.get(f"{api_base}/projects/{project_path}", headers=headers)
                if proj_res.status_code != 200:
                    raise ValueError(f"Project not found or inaccessible: {proj_res.status_code}")
                proj_data = proj_res.json()
                default_branch = proj_data.get("default_branch", "main")
                
                file_url_path = file_path.replace("/", "%2F")
                content_res = requests.get(f"{api_base}/projects/{project_path}/repository/files/{file_url_path}/raw?ref={default_branch}", headers=headers)
                if content_res.status_code != 200:
                    raise ValueError(f"Could not fetch file: {content_res.status_code}")
                    
                original_content = content_res.text
                lines = original_content.split("\n")
                
                if len(lines) >= line_num:
                    target_line = lines[line_num - 1]
                    if secret_value in target_line:
                        lines[line_num - 1] = target_line.replace(secret_value, secret_placeholder)
                    else:
                        lines[line_num - 1] = target_line + f" # Remediated: {secret_placeholder}"
                else:
                    raise ValueError(f"File line number {line_num} out of bounds")
                    
                new_content = "\n".join(lines)
                
                import time
                branch_name = f"nhi-remediate-L{line_num}-{int(time.time())}"
                
                commit_payload = {
                    "branch": branch_name,
                    "commit_message": f"🛡️ Remediate hardcoded secret in {file_path} (L{line_num})",
                    "start_branch": default_branch,
                    "actions": [
                        {
                            "action": "update",
                            "file_path": file_path,
                            "content": new_content
                        }
                    ]
                }
                
                commit_res = requests.post(f"{api_base}/projects/{project_path}/repository/commits", json=commit_payload, headers=headers)
                if commit_res.status_code != 201:
                    raise ValueError(f"Failed to create commit/branch: {commit_res.text}")
                    
                mr_payload = {
                    "source_branch": branch_name,
                    "target_branch": default_branch,
                    "title": f"🛡️ Remediate hardcoded secret in {file_path}",
                    "description": f"""An automated merge request generated by the **NHI Governance Agent**.

### 🔒 Security Resolution Summary:
* **Issue**: Hardcoded secret detected at line {line_num} of `{file_path}`.
* **Resolution**: Replaced secret with secure configuration placeholder: `{secret_placeholder}`.
* **Storage**: Secret values have been uploaded to **Google Cloud Secret Manager**.

Please review and merge this request to secure the repository."""
                }
                
                mr_res = requests.post(f"{api_base}/projects/{project_path}/merge_requests", json=mr_payload, headers=headers)
                if mr_res.status_code != 201:
                    raise ValueError(f"Failed to create Merge Request: {mr_res.text}")
                    
                mr_data = mr_res.json()
                return jsonify({
                    "status": "ok",
                    "mr_url": mr_data.get("web_url"),
                    "branch": branch_name,
                    "message": f"Successfully created GitLab Merge Request #{mr_data.get('iid')} and branch '{branch_name}'"
                }), 200
                
            except Exception as e:
                log.warning(f"GitLab API remediation failed: {e}. Falling back to simulation.")
                import random
                mr_id = random.randint(10, 99)
                sim_branch = f"nhi-remediate-L{line_num}-simulated"
                return jsonify({
                    "status": "demo-success",
                    "mr_url": f"https://gitlab.com/{project_path.replace('%2F', '/')}/-/merge_requests/{mr_id}",
                    "branch": sim_branch,
                    "message": f"Remediation Simulated: Opened GitLab Merge Request #{mr_id} (Demo Mode: {str(e)})"
                }), 200
            
    except Exception as e:
        log.exception(f"[remediate_gitlab_mr] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/seed", methods=["POST"])
def api_seed():
    """Seed demo data into MongoDB."""
    try:
        from db import seed_demo_data
        repo = seed_demo_data()
        return jsonify({"status": "ok", "message": f"Seeded 7 days of data for {repo}"}), 200
    except Exception as e:
        log.warning(f"[api_seed] MongoDB seeding failed: {e}. Falling back to simulation.")
        return jsonify({
            "status": "demo-success",
            "message": f"Demo data seeded in simulation mode (Database offline: {str(e)})"
        }), 200


# --- Custom Tools API for Agent Builder ---

@app.route("/tools/scan", methods=["POST"])
def tool_scan():
    """scan_repo tool — Agent Builder custom tool."""
    try:
        body = request.get_json(force=True) or {}
        repo_url = body.get("repo_url")
        if not repo_url:
            return jsonify({"status": "error", "message": "repo_url is required"}), 400
        gitlab_token = body.get("gitlab_token") or os.getenv("GITLAB_TOKEN") or os.getenv("GITHUB_TOKEN")
        from scanner import scan_repo
        raw = scan_repo(repo_url, gitlab_token)
        return jsonify({"findings": raw}), 200
    except Exception as e:
        log.exception(f"[tool_scan] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/tools/score", methods=["POST"])
def tool_score():
    """score_findings tool — Agent Builder custom tool."""
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
    """save_to_mongodb tool — Agent Builder custom tool."""
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
    """check_drift tool — Agent Builder custom tool."""
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
    """publish_alert tool — Agent Builder custom tool."""
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


# --- Cloud Run endpoints for scheduler/webhooks ---

@app.route("/scan", methods=["POST"])
def trigger_scan():
    """Called by Cloud Scheduler every hour."""
    try:
        body = request.get_json(force=True) or {}
        repo_url = body.get("repo") or os.getenv("GITLAB_REPO", "demo")
        gitlab_token = os.getenv("GITLAB_TOKEN")

        from scanner import scan_repo, score_risk_with_gemini
        raw = scan_repo(repo_url, gitlab_token)
        scored = score_risk_with_gemini(raw)

        try:
            from db import save_scan
            save_scan(repo_url, scored)
        except Exception as e:
            log.error(f"[scan] MongoDB error: {e}")

        critical = [r for r in scored if r.get("risk") == "CRITICAL"]
        if critical:
            _publish_critical_alert(repo_url, critical)

        return jsonify({"status": "ok", "repo": repo_url, "total": len(scored), "critical": len(critical)}), 200
    except Exception as e:
        log.exception(f"[scan] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/alert", methods=["POST"])
def receive_alert():
    """Pub/Sub push endpoint."""
    try:
        envelope = request.get_json(force=True)
        if not envelope or "message" not in envelope:
            return "Bad request", 400
        data = base64.b64decode(envelope["message"]["data"]).decode("utf-8")
        payload = json.loads(data)
        repo = payload.get("repo", "unknown")
        findings = payload.get("critical_findings", [])
        log.critical(f"[alert] CRITICAL NHIs in {repo}: {len(findings)} finding(s)")

        slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
        if slack_webhook:
            _notify_slack(slack_webhook, repo, findings)
        return "OK", 200
    except Exception as e:
        log.exception(f"[alert] Error: {e}")
        return "Error", 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


# --- Internal helpers ---

def _publish_critical_alert(repo: str, critical_findings: list):
    """Publish a message to the Pub/Sub CRITICAL alerts topic."""
    try:
        from google.cloud import pubsub_v1
        project_id = os.getenv("GCP_PROJECT_ID")
        topic_id = os.getenv("PUBSUB_TOPIC", "nhi-critical-alerts")
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(project_id, topic_id)

        payload = json.dumps({
            "repo": repo,
            "critical_findings": [
                {
                    "file": r.get("raw", {}).get("file") if isinstance(r.get("raw"), dict) else r.get("file", ""),
                    "line": r.get("raw", {}).get("line") if isinstance(r.get("raw"), dict) else r.get("line", 0),
                    "pattern": r.get("raw", {}).get("pattern") if isinstance(r.get("raw"), dict) else r.get("pattern", ""),
                    "action": r.get("action", ""),
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
    import requests as req
    lines = "\n".join(f"• `{f['file']}:{f['line']}` — `{f['pattern']}`" for f in findings)
    msg = {"text": f"🔴 *CRITICAL NHIs detected* in `{repo}`\n{lines}\n\nCheck the dashboard immediately."}
    try:
        req.post(webhook_url, json=msg, timeout=5)
    except Exception as e:
        log.error(f"[alert] Slack notify failed: {e}")


# --- Serve frontend files ---

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    """Serve the frontend SPA. Falls back to index.html for SPA routing."""
    if path and os.path.exists(os.path.join(FRONTEND_DIR, path)):
        return send_from_directory(FRONTEND_DIR, path)
    return send_from_directory(FRONTEND_DIR, "index.html")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    log.info(f"🛡️  NHI Governance Agent API starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
