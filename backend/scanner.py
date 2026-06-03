import os
import sys
import json
import requests
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
import google.generativeai as genai

# Reconfigure stdout to use utf-8 to avoid UnicodeEncodeErrors on Windows terminals when printing emojis
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


load_dotenv(override=True)

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.0-flash")

NHI_PATTERNS = [
    "api_key", "API_KEY",
    "secret", "SECRET",
    "token", "TOKEN",
    "password", "PASSWORD",
    "private_key", "PRIVATE_KEY",
    "access_key", "ACCESS_KEY",
    "client_secret", "CLIENT_SECRET",
    "auth_token", "AUTH_TOKEN",
]

HEURISTIC_RISK = {
    "api_key":       ("CRITICAL", "Hardcoded API key"),
    "private_key":   ("CRITICAL", "Hardcoded private key"),
    "client_secret": ("CRITICAL", "Hardcoded client secret"),
    "password":      ("CRITICAL", "Hardcoded password"),
    "secret":        ("HIGH",     "Hardcoded secret value"),
    "auth_token":    ("HIGH",     "Hardcoded auth token"),
    "access_key":    ("HIGH",     "Hardcoded access key"),
    "token":         ("MEDIUM",   "Hardcoded token"),
}


def scan_gitlab_repo(repo_url, gitlab_token=None):
    if repo_url.strip().lower() == "demo":
        return _demo_findings()

    # Clean the URL to ignore query strings or fragment identifiers
    clean_url = repo_url.split("?")[0].split("#")[0].strip().rstrip("/")
    parts = clean_url.split("gitlab.com/")
    if len(parts) < 2:
        print(f"Invalid GitLab URL: {repo_url}")
        return []

    project_path_str = parts[1]
    if project_path_str.endswith(".git"):
        project_path_str = project_path_str[:-4]
    project_path_str = project_path_str.lstrip("/")
    project_path = project_path_str.replace("/", "%2F")
    
    api_base = "https://gitlab.com/api/v4"

    headers = {}
    if gitlab_token and not gitlab_token.startswith("glpat-xxxx"):
        headers["PRIVATE-TOKEN"] = gitlab_token

    # Retrieve default branch dynamically
    project_url = f"{api_base}/projects/{project_path}"
    project_response = requests.get(project_url, headers=headers)
    if project_response.status_code == 404:
        raise ValueError("GitLab repository not found. Please verify the URL is correct and public.")
    elif project_response.status_code in [401, 403]:
        raise ValueError("GitLab repository is private or access is unauthorized. Please verify your token.")
    elif project_response.status_code != 200:
        raise ValueError(f"Error accessing GitLab repository metadata: {project_response.status_code}")
    
    project_data = project_response.json()
    default_branch = project_data.get("default_branch", "main")

    # fetch zip of the repo
    archive_url = f"{api_base}/projects/{project_path}/repository/archive.zip?ref={default_branch}"
    print(f"fetching zip from gitlab: {archive_url}")
    response = requests.get(archive_url, headers=headers)

    if response.status_code == 404:
        raise ValueError("GitLab repository archive not found. Please verify the branch/ref.")
    elif response.status_code != 200:
        raise ValueError(f"Error downloading GitLab repository archive: {response.status_code}")

    import io
    import zipfile

    found_nhis = []
    try:
        z = zipfile.ZipFile(io.BytesIO(response.content))
        file_list = z.namelist()
        print(f"got {len(file_list)} files from zip, scanning them now...")

        for name in file_list:
            # Skip directories
            if name.endswith('/'):
                continue
            
            # Check text extensions
            if not any(name.endswith(ext) for ext in 
                       [".py", ".js", ".ts", ".env", ".yml", ".yaml", 
                        ".json", ".sh", ".tf", ".config"]):
                continue

            # Strip the top-level directory name from ZIP entry path
            # (GitLab wraps archives in a root directory named 'project-name-commit-hash')
            path_parts = name.split('/', 1)
            repo_relative_path = path_parts[1] if len(path_parts) > 1 else name

            try:
                with z.open(name) as f:
                    content = f.read().decode('utf-8', errors='ignore')
                
                for line_num, line in enumerate(content.split("\n"), 1):
                    for pattern in NHI_PATTERNS:
                        if pattern.lower() in line.lower():
                            found_nhis.append({
                                "file": repo_relative_path,
                                "line": line_num,
                                "content": line.strip()[:100],
                                "pattern": pattern
                            })
                            break
            except Exception:
                # Silently skip file reading failures
                pass
                
    except Exception as e:
        print(f"❌ Error during ZIP parsing: {e}")
        return []

    return found_nhis


def _demo_findings():
    return [
        {"file": "deploy/k8s/secrets.yml", "line": 12, "pattern": "api_key",       "content": "api_key: sk-prod-xxxxxxxxxxxxxxxx"},
        {"file": ".env.production",        "line": 4,  "pattern": "password",      "content": "DB_PASSWORD=Sup3rS3cr3t!"},
        {"file": "ci/pipeline.yml",        "line": 33, "pattern": "token",         "content": "GITLAB_TOKEN: glpat-xxxxxxxxxxxx"},
        {"file": "src/integrations/aws.py","line": 8,  "pattern": "access_key",    "content": "ACCESS_KEY_ID = 'AKIAIOSFODNN7EXAMPLE'"},
        {"file": "terraform/main.tf",      "line": 21, "pattern": "client_secret", "content": "client_secret = var.azure_secret"},
    ]

def fetch_gitlab_user_repos(owner, token=None, is_group=False):
    import requests
    headers = {}
    if token and not token.startswith("glpat-xxxx") and not token.startswith("ghp_xxxx"):
        headers["PRIVATE-TOKEN"] = token
        
    api_base = "https://gitlab.com/api/v4"
    if is_group:
        url = f"{api_base}/groups/{owner}/projects?per_page=100"
    else:
        url = f"{api_base}/users/{owner}/projects?per_page=100"
        
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            return [p.get("web_url") for p in res.json()]
        elif not is_group:
            # Fallback to group
            url_fallback = f"{api_base}/groups/{owner}/projects?per_page=100"
            res_fallback = requests.get(url_fallback, headers=headers, timeout=8)
            if res_fallback.status_code == 200:
                return [p.get("web_url") for p in res_fallback.json()]
    except Exception as e:
        print(f"Error fetching GitLab repos: {e}")
    return []

def fetch_github_user_repos(owner, token=None):
    url = f"https://api.github.com/users/{owner}/repos?per_page=100&sort=updated"
    headers = {"User-Agent": "nhi-agent"}
    if token and not token.startswith("ghp_xxxx") and not token.startswith("glpat-xxxx"):
        headers["Authorization"] = f"token {token}"
    try:
        import requests
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            return [f"https://github.com/{owner}/{r['name']}" for r in res.json()]
    except Exception as e:
        print(f"Error fetching GitHub repos: {e}")
    return []


def scan_github_repo(repo_url, github_token=None):
    clean_url = repo_url.split("?")[0].split("#")[0].strip().rstrip("/")
    parts = clean_url.split("github.com/")
    if len(parts) < 2:
        print(f"Invalid GitHub URL: {repo_url}")
        return []

    path_parts = parts[1].lstrip("/").split("/")
    if len(path_parts) < 2:
        print(f"Profile URL detected: {repo_url}")
        return []

    owner = path_parts[0]
    repo = path_parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    archive_url = f"https://api.github.com/repos/{owner}/{repo}/zipball"
    headers = {"User-Agent": "nhi-agent"}
    if github_token and not github_token.startswith("ghp_xxxx") and not github_token.startswith("glpat-xxxx"):
        headers["Authorization"] = f"token {github_token}"

    import requests
    # Check repository metadata first to verify existence/access
    repo_meta_url = f"https://api.github.com/repos/{owner}/{repo}"
    meta_res = requests.get(repo_meta_url, headers=headers)
    if meta_res.status_code == 404:
        raise ValueError(f"GitHub repository '{owner}/{repo}' not found. Please verify the URL is correct and public.")
    elif meta_res.status_code in [401, 403]:
        raise ValueError(f"GitHub repository '{owner}/{repo}' is private or access is unauthorized. Please verify your token.")
    elif meta_res.status_code != 200:
        raise ValueError(f"Error accessing GitHub repository metadata: {meta_res.status_code}")

    print(f"fetching zip from github: {archive_url}")
    response = requests.get(archive_url, headers=headers)
    if response.status_code == 404:
        raise ValueError("GitHub repository archive not found.")
    elif response.status_code != 200:
        raise ValueError(f"Error downloading GitHub repository archive: {response.status_code}")

    import io
    import zipfile

    found_nhis = []
    try:
        z = zipfile.ZipFile(io.BytesIO(response.content))
        file_list = z.namelist()
        print(f"got {len(file_list)} files from zip, scanning them now...")

        for name in file_list:
            if name.endswith('/'):
                continue
            
            # Check text extensions
            if not any(name.endswith(ext) for ext in 
                       [".py", ".js", ".ts", ".env", ".yml", ".yaml", 
                        ".json", ".sh", ".tf", ".config", ".md"]):
                continue

            parts_in_name = name.split('/', 1)
            repo_relative_path = parts_in_name[1] if len(parts_in_name) > 1 else name

            try:
                with z.open(name) as f:
                    content = f.read().decode('utf-8', errors='ignore')
                
                for line_num, line in enumerate(content.split("\n"), 1):
                    for pattern in NHI_PATTERNS:
                        if pattern.lower() in line.lower():
                            found_nhis.append({
                                "file": repo_relative_path,
                                "line": line_num,
                                "content": line.strip()[:100],
                                "pattern": pattern
                            })
                            break
            except Exception:
                pass
    except Exception as e:
        print(f"❌ Error during ZIP parsing: {e}")
        return []

    return found_nhis


def scan_repo(repo_url, token=None):
    if repo_url.strip().lower() == "demo":
        return _demo_findings()
    if "github.com" in repo_url.lower():
        return scan_github_repo(repo_url, token)
    else:
        return scan_gitlab_repo(repo_url, token)

def score_risk_with_gemini(nhis):
    if not nhis:
        print("No NHIs found.")
        return []

    print(f"scoring {len(nhis)} potential secrets with gemini...")
    scored = []

    for nhi in nhis:
        try:
            prompt = f"""You are a security expert analyzing Non-Human Identities (NHIs) in code.

Analyze this potential credential found in code:
File: {nhi['file']}
Line {nhi['line']}: {nhi['content']}

Respond in this exact format:
RISK: [CRITICAL/HIGH/MEDIUM/LOW]
TYPE: [what kind of credential this likely is]
REASON: [one sentence why this is risky or not]
ACTION: [one sentence what should be done]
BREACH_COST: [estimated financial breach cost in USD based strictly on credential type: cloud provider keys (AWS, GCP, Azure) = $2-5M; database passwords/credentials = $500K-1M; session secrets/Flask keys/encryption keys = $50-200K; generic API tokens/webhooks/keys = $100-500K. Format strictly as e.g. $4.5M or $120k]
BLAST_RADIUS: [one sentence describing exactly what systems or data are exposed by this key]
"""
            response    = model.generate_content(prompt)
            result_text = response.text.strip()
            parsed      = {"raw": nhi}

            for line in result_text.split("\n"):
                if line.startswith("RISK:"):          parsed["risk"]   = line.replace("RISK:", "").strip()
                elif line.startswith("TYPE:"):        parsed["type"]   = line.replace("TYPE:", "").strip()
                elif line.startswith("REASON:"):      parsed["reason"] = line.replace("REASON:", "").strip()
                elif line.startswith("ACTION:"):      parsed["action"] = line.replace("ACTION:", "").strip()
                elif line.startswith("BREACH_COST:"):  parsed["breach_cost"] = line.replace("BREACH_COST:", "").strip()
                elif line.startswith("BLAST_RADIUS:"): parsed["blast_radius"] = line.replace("BLAST_RADIUS:", "").strip()

        except Exception as e:
            print(f"[!] Gemini API error ({type(e).__name__}). Applying robust heuristic analysis.")
            key  = nhi["pattern"].lower()
            risk, cred_type = HEURISTIC_RISK.get(key, ("MEDIUM", "Hardcoded credential"))
            
            reason_map = {
                "api_key": "Hardcoded API key detected in source file, presenting immediate access risk to external services.",
                "private_key": "Plaintext private key exposed in source code, potentially compromising host and data encryption.",
                "client_secret": "Application client secret exposed in source code, enabling third-party impersonation.",
                "password": "Plaintext password credential hardcoded in file configuration.",
                "secret": "Plaintext credential secret hardcoded in configuration context.",
                "auth_token": "Authorization token exposed in plaintext code.",
                "access_key": "Access key identifier found in code, which could lead to unauthorized API access.",
                "token": "Authentication token hardcoded in plaintext configuration."
            }
            reason = reason_map.get(key, f"Hardcoded '{nhi['pattern']}' credential found in source file configuration.")
            
            cost_map = {
                "api_key":       ("$300k", "Access to external SaaS integrations and customer APIs."),
                "private_key":   ("$4.5M", "Full server compromise, unauthorized decryption of secure payloads, and host access."),
                "client_secret": ("$250k", "Third-party application impersonation and credential stuffing vulnerabilities."),
                "password":      ("$850k", "Direct access to application database nodes and administrative accounts."),
                "secret":        ("$120k", "Unauthorized decryption of session cookies, session hijacking, and application impersonation."),
                "auth_token":    ("$350k", "Impersonation of users or CI/CD runner environments."),
                "access_key":    ("$4.2M", "Unauthorized read/write access to Cloud Storage buckets and resources."),
                "token":         ("$150k", "Access to developer tools, codebases, or testing servers.")
            }
            cost, blast = cost_map.get(key, ("$200k", "Access to internal configurations and helper modules."))
            
            parsed = {
                "raw":          nhi,
                "risk":         risk,
                "type":         cred_type,
                "reason":       reason,
                "action":       "Rotate this credential immediately and migrate storage to Google Cloud Secret Manager.",
                "breach_cost":  cost,
                "blast_radius": blast
            }

        scored.append(parsed)
        risk  = parsed.get("risk", "UNKNOWN")
        emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(risk, "⚪")
        print(f"{emoji} [{risk}] {nhi['file']}:{nhi['line']}")
        print(f"   Type:   {parsed.get('type', 'Unknown')}")
        print(f"   Reason: {parsed.get('reason', 'N/A')}")
        print(f"   Action: {parsed.get('action', 'N/A')}")
        print()

    return scored


def generate_report(scored_nhis):
    if not scored_nhis:
        print("No secrets found. Repo looks clean!")
        return

    critical = [n for n in scored_nhis if n.get("risk") == "CRITICAL"]
    high     = [n for n in scored_nhis if n.get("risk") == "HIGH"]
    medium   = [n for n in scored_nhis if n.get("risk") == "MEDIUM"]
    low      = [n for n in scored_nhis if n.get("risk") == "LOW"]

    print("\n--- NHI Scan Report ---")
    print(f"Critical: {len(critical)}")
    print(f"High: {len(high)}")
    print(f"Medium: {len(medium)}")
    print(f"Low: {len(low)}")
    print(f"Total findings: {len(scored_nhis)}")
    print("-----------------------")

    if critical:
        print("\nFix these critical leaks ASAP:")
        for n in critical:
            print(f"   -> {n['raw']['file']}:{n['raw']['line']}")


if __name__ == "__main__":
    print("NHI Governance Agent Scanner CLI\n")

    repo_url     = input("Enter GitLab/GitHub repo URL (or 'demo'): ")
    gitlab_token = input("Enter token (optional): ").strip()

    nhis   = scan_gitlab_repo(repo_url, gitlab_token if gitlab_token else None)
    scored = score_risk_with_gemini(nhis)
    generate_report(scored)

    mongo_uri = os.getenv("MONGO_URI")
    if mongo_uri:
        try:
            from db import save_scan
            scan_id = save_scan(repo_url, scored)
            print(f"\nSaved scan to database (ID: {scan_id})")
        except Exception as e:
            print(f"\nCould not save to db: {e}")
    else:
        print("\nAdd MONGO_URI to .env to save scan runs.")


def generate_code_patch(file_content, line_num, secret_value, secret_placeholder):
    """
    Use Gemini 2.0 Flash to analyze the code context, generate a clean
    replacement line, a diff block, and a WIF recommendation if the secret is a cloud key.
    """
    lines = file_content.split("\n")
    # Get context: 5 lines before, 5 lines after
    start_idx = max(0, line_num - 6)
    end_idx = min(len(lines), line_num + 5)
    
    context_lines = []
    for idx in range(start_idx, end_idx):
        prefix = "--> " if idx == line_num - 1 else "    "
        context_lines.append(f"{idx+1:4d} | {prefix}{lines[idx]}")
        
    context_str = "\n".join(context_lines)
    
    prompt = f"""You are a senior security engineer. Help remediate a hardcoded secret in a repository.

Here is the context around line {line_num}:
```
{context_str}
```

The secret value to replace is: "{secret_value}"
The suggested secure replacement placeholder (which reads from env/Secret Manager) is: "{secret_placeholder}"

Perform two tasks:
1. Generate the exact replacement line(s) for line {line_num} that swaps the hardcoded secret for the placeholder. Keep the exact indentation and syntax of the surrounding code.
   If the language is Python, do NOT silently fetch from the environment allowing a None value in runtime. For critical variables like database passwords, API keys, or session secrets (e.g. app.secret_key), avoid using .get() and instead use direct bracket access (e.g., `os.environ['SECRET_KEY']`) so that Python raises a KeyError if the environment variable is not configured, or raise an explicit ValueError, and append a trailing comment `# REQUIRED: Must be set in environment variables` at the end of the line. Ensure the replacement is syntactically valid.
2. Determine if this secret is a Cloud Provider Key (like AWS, Azure, or GCP credentials). If it is, write a step-by-step recommendation explaining how to use Workload Identity Federation (WIF) or IAM Roles instead of hardcoded keys (including Terraform or gcloud CLI commands). If it is not a cloud key (e.g. it is a database password, general webhook, or generic API token), write "No Workload Identity Federation recommendation applicable. Continue storing in Secret Manager."

Return your response in this exact JSON format (do not include any markdown outside of the JSON block):
{{
  "original_line": "the exact original line at line {line_num}",
  "remediated_line": "the exact remediated line with the placeholder",
  "explanation": "one sentence explaining the change",
  "code_patch": "a unified diff-like visual block showing the before and after lines",
  "wif_recommendation": "the step-by-step migration guide for WIF if applicable, or the default sentence"
}}
"""
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        # Clean up any potential markdown code blocks like ```json ... ```
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        parsed = json.loads(text)
        return parsed
    except Exception as e:
        # Fallback if Gemini fails (e.g., API quota exceeded)
        print(f"[!] Gemini API error ({type(e).__name__}) during patch generation. Applying robust fallback patcher.")
        target_line = lines[line_num - 1] if len(lines) >= line_num else ""
        remediated_line = target_line.replace(secret_value, secret_placeholder) if secret_value in target_line else target_line
        
        # Append warning comment to Python remediation if using environment variables
        if file_content and "os.environ" in remediated_line:
            remediated_line = remediated_line.rstrip() + "  # REQUIRED: Must be set in environment variables"
        
        diff = f"- {target_line.strip()}\n+ {remediated_line.strip()}"
        
        is_cloud = any(k in secret_value.lower() or k in secret_placeholder.lower() or k in file_content.lower()
                       for k in ["aws", "amazon", "gcp", "google", "azure", "private_key", "access_key"])
        
        if is_cloud:
            wif_guide = """To secure this cloud key, transition to Workload Identity Federation (WIF):
1. Create a Workload Identity Pool:
   gcloud iam workload-identity-pools create "nhi-pool" --location="global"
2. Connect your Git provider as an OIDC Identity Provider.
3. Grant IAM permissions to the Workload Identity Pool instead of using a long-lived private key.
4. Update your CI/CD configuration to authenticate using the generated federation token."""
        else:
            wif_guide = "No Workload Identity Federation recommendation applicable. Continue storing in Secret Manager."
            
        return {
            "original_line": target_line,
            "remediated_line": remediated_line,
            "explanation": "Substituted plaintext credential with configuration environment pointer to eliminate plaintext credential exposure.",
            "code_patch": diff,
            "wif_recommendation": wif_guide
        }
