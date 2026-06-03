import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🧪 Testing GitHub Remediation API endpoint...")

def make_request(url, method="POST", data=None):
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    json_data = json.dumps(data).encode("utf-8") if data else None
    try:
        with urllib.request.urlopen(req, data=json_data) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except Exception as e:
        return 500, str(e)

# Test GitHub PR endpoint
github_payload = {
    "repo_url": "https://github.com/rivcoder/Web-Innovations",
    "file_path": "CityCare/app.py",
    "line": 11,
    "secret_value": "test-secret-value",
    "secret_placeholder": "os.environ.get('SECRET_CITYCARE_APP_PY_L11')"
}
status, res = make_request("http://localhost:8080/api/remediate/gitlab-mr", data=github_payload)
print(f"\nGitHub PR Remediation status={status}")
print(f"Response: {res}")
