# 🛡️ NHI Governance Agent

> **AI-powered Non-Human Identity lifecycle governance for GitLab and GitHub repositories.**
> Built for the Google Cloud Rapid Agent Hackathon 2026.

---
> 🌐 **Live Demo**: https://nhi-agent-production.up.railway.app
## The Problem

74% of organizations deploying AI agents have no governance over the credentials those agents use. Traditional secret scanners (GitGuardian, TruffleHog) tell you *if* a secret exists at a point in time. Nobody tells you *how that secret's risk is silently growing* — or what it would cost if it leaked today.

Non-Human Identities (NHIs) — API keys, service tokens, database passwords, cloud credentials — are the attack surface nobody is watching. NIST issued a Request for Information on AI Agent Identity in early 2026. The tooling is 12-18 months behind the threat.

**This agent closes that gap.**

---

## What It Does

The NHI Governance Agent is a closed-loop security agent that:

1. **Scans** GitLab and GitHub repositories for hardcoded credentials across code, CI/CD configs, Terraform, and environment files
2. **Scores** each finding using Gemini 2.0 Flash with full code context — not just regex pattern matching
3. **Estimates** financial breach cost and blast radius per credential type ($50K for a session secret, $2-5M for an exposed cloud provider key)
4. **Tracks** every identity over time in MongoDB — detecting when a credential's risk silently escalates across scans
5. **Remediates** autonomously — generates a code diff, creates a branch, uploads the secret to GCP Secret Manager, and opens a Merge Request / Pull Request
6. **Alerts** in real time via Cloud Pub/Sub when any finding crosses a CRITICAL threshold

The key differentiator: **drift detection**. When an AWS key goes from LOW risk on Monday to CRITICAL by Friday because it was promoted from dev to a production config — your agent catches it. No existing tool does this.

---

## Architecture

```
GitLab MCP / GitHub API
        ↓
Google Cloud Agent Builder  ←── Cloud Scheduler (hourly trigger)
        ↓
  Gemini 2.0 Flash
  (risk scoring + remediation generation)
        ↓
  Python extraction layer
  (NHI patterns, breach cost, blast radius)
        ↓
  MongoDB Atlas
  (nhi_index + scans collections, drift tracking)
        ↓
  Cloud Pub/Sub  ──→  Cloud Run alert handler  ──→  Slack
        ↓
  Streamlit / Custom Web Console
  (glassmorphic UI, SVG health ring, drift chart)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI reasoning | Gemini 2.0 Flash via Vertex AI |
| Orchestration | Google Cloud Agent Builder |
| Source scanning | GitLab MCP + GitHub API |
| Storage | MongoDB Atlas ($facet aggregation pipeline) |
| Alerting | Google Cloud Pub/Sub |
| Deployment | Google Cloud Run |
| Scheduling | Google Cloud Scheduler |
| Secrets | Google Cloud Secret Manager |
| Backend | Python / Flask |
| Frontend | Vanilla HTML/CSS/JS (custom glassmorphic console) |

---

## Partner Track Integrations

### GitLab MCP
The agent uses GitLab's Model Context Protocol server to scan repositories, CI/CD pipeline configs, merge requests, and service account configurations. Write-back creates branches, commits code fixes, and opens Merge Requests autonomously — a full read/write agentic loop, not a passive reporting tool.

### MongoDB Atlas
Two collections power the governance layer:

- **`scans`** — one document per scan run with full findings and risk summary
- **`nhi_index`** — one document per unique NHI identity, updated on every scan with a `history[]` array

The Security Posture Health score, Remediation Rate, and Mean Time to Remediate (MTTR) are calculated via a parallel `$facet` aggregation pipeline — not basic CRUD. The `nhi_index` history array enables drift detection: comparing the last two snapshots to flag any identity that changed risk level between scans.

---

## Key Features

### Security Posture Health Score
Circular SVG progress ring showing an aggregated score (0-100) weighted by active credential severity. Backed by MongoDB `$facet` aggregation across the full identity index.

### Breach Cost & Blast Radius
Per-finding financial impact estimate driven by credential type:
- Cloud provider keys (AWS/GCP/Azure): $2-5M USD
- Database credentials: $500K-1M USD  
- Session secrets and Flask keys: $50-200K USD
- Generic API tokens: $100-500K USD

### Gemini Remediation Assistant
On-demand code diff generation, Workload Identity Federation migration guide, and automatic Secret Manager upload. The generated diff uses bracket syntax (`os.environ['SECRET_NAME']`) rather than `.get()` fallbacks — so if the environment variable isn't set, Python raises an immediate `KeyError` instead of silently using the hardcoded value.

### History & Drift Tab
Line chart of risk counts across all scans, powered by MongoDB time-series snapshots. Drift alerts surface any NHI that changed risk level between its last two scans. This is the feature no existing tool has.

### Autonomous Remediation Loop
1. Gemini generates the code patch
2. Agent creates a new branch in GitLab/GitHub
3. Secret is uploaded to GCP Secret Manager
4. Merge Request / Pull Request is opened with full context
5. Human reviews and approves — the agent handles everything else

---

## Local Setup

```bash
# 1. Clone and install
git clone https://gitlab.com/your-org/nhi-governance-agent
cd nhi-governance-agent
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Fill in: GEMINI_API_KEY, MONGO_URI, GITLAB_TOKEN, GCP_PROJECT_ID

# 3. Seed demo data
python -c "from backend.db import seed_demo_data; seed_demo_data()"

# 4. Start backend
python backend/server.py

# 5. Open frontend
# Visit http://localhost:8080
```

---

## GCP Deployment

```bash
# Prerequisites: gcloud CLI installed and authenticated
export GEMINI_API_KEY=...
export MONGO_URI=...
export GITLAB_TOKEN=...

# Edit PROJECT_ID at top of deploy.sh, then:
bash agent_builder/deploy.sh
```

This single script:
- Enables all required GCP APIs
- Creates a service account with least-privilege IAM roles
- Stores secrets in Secret Manager
- Creates the Pub/Sub topic and push subscription
- Deploys the agent to Cloud Run
- Creates a Cloud Scheduler job for hourly scans

---

## Demo

Click **Demo** in the console to load a pre-seeded 7-day scenario:

- 5 NHIs tracked across `acme-payments` repository
- `src/integrations/aws.py` ACCESS_KEY escalates LOW → CRITICAL over 7 days
- No human noticed. The agent did.
- History & Drift tab shows the full escalation timeline
- Click any finding → Ask Gemini Remediation Assistant → see the code diff and WIF migration guide
---

## Why This Wins

| Capability | GitGuardian | TruffleHog | NHI Governance Agent |
|---|---|---|---|
| Secret detection | ✅ | ✅ | ✅ |
| Risk scoring with AI context | ❌ | ❌ | ✅ |
| Drift tracking over time | ❌ | ❌ | ✅ |
| Financial breach cost estimate | ❌ | ❌ | ✅ |
| Autonomous code fix + MR | ❌ | ❌ | ✅ |
| GCP Secret Manager upload | ❌ | ❌ | ✅ |
| Agentic lifecycle (not point-in-time) | ❌ | ❌ | ✅ |

---

## Team

Built for the Google Cloud Rapid Agent Hackathon 2026.

---

## License

MIT
