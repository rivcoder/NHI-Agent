# 🛡️ NHI Governance Agent — Demo Script
# Use this as your presentation talking points (3-5 minutes)

# ══════════════════════════════════════════════════════════════════
# SLIDE 1: THE PROBLEM (30 seconds)
# ══════════════════════════════════════════════════════════════════
#
# "Every organization has Non-Human Identities — API keys, service
# tokens, database passwords — hardcoded in their source code.
#
# The average company has 17x more NHIs than human employees.
# And 80% of breaches involve compromised credentials.
#
# The problem? Nobody is governing these identities.
# Nobody tracks when permissions escalate. Nobody alerts when
# a LOW-risk token suddenly becomes CRITICAL."


# ══════════════════════════════════════════════════════════════════
# SLIDE 2: THE SOLUTION (30 seconds)
# ══════════════════════════════════════════════════════════════════
#
# "We built an AI-powered NHI Governance Agent using Google Cloud.
#
# It does 4 things:
#   1. SCANS GitLab repos for hardcoded credentials
#   2. SCORES each finding with Gemini AI — not just pattern matching
#   3. TRACKS permission drift over time
#   4. ALERTS your team when something goes CRITICAL
#
# It runs automatically every hour via Cloud Scheduler."


# ══════════════════════════════════════════════════════════════════
# SLIDE 3: LIVE DEMO (2 minutes)
# ══════════════════════════════════════════════════════════════════
#
# Step 1: Open http://localhost:8501
#         → Show the clean Streamlit dashboard
#
# Step 2: Click 🎭 Demo in the sidebar
#         → Watch Gemini score 5 findings in real-time
#         → Point out: "Gemini doesn't just match patterns —
#           it understands CONTEXT. It knows terraform variables
#           are MEDIUM risk, while hardcoded AWS keys are CRITICAL."
#
# Step 3: Show the findings panel
#         → Expand a CRITICAL finding
#         → Show: Risk level, Type, Reason, Action
#         → "Each finding gets a specific remediation action"
#
# Step 4: Show the Export panel
#         → Click "Download CSV"
#         → "Security teams get actionable reports"
#
# Step 5: Switch to "History & Drift" tab
#         → Click "Seed demo data" in sidebar first (if MongoDB connected)
#         → Show the risk trend chart
#         → Point out: "See this? Agent #3 — an AWS access key —
#           escalated from LOW to CRITICAL over 7 days.
#           Our agent caught the drift automatically."
#
# Step 6: Switch to "NHI Index" tab
#         → Show the centralized identity inventory
#         → Expand the aws.py entry with ⚡ drift indicator
#         → Show the mini drift chart
#         → "Every NHI is tracked as a unique identity across scans"


# ══════════════════════════════════════════════════════════════════
# SLIDE 4: ARCHITECTURE (30 seconds)
# ══════════════════════════════════════════════════════════════════
#
# "Under the hood:
#   - Scanner hits the GitLab API, pulls code, pattern-matches
#   - Gemini 2.0 Flash scores each finding with security expertise
#   - If Gemini is down, we fall back to heuristic scoring — zero downtime
#   - MongoDB Atlas persists everything for drift analysis
#   - Cloud Run + Pub/Sub handles automated scanning and alerts
#   - Agent Builder orchestrates the entire workflow"


# ══════════════════════════════════════════════════════════════════
# SLIDE 5: WHAT MAKES THIS DIFFERENT (30 seconds)
# ══════════════════════════════════════════════════════════════════
#
# "Three things make us different from existing secret scanners:
#
#   1. AI-POWERED SCORING — Gemini understands context, not just regex.
#      It knows the difference between a variable named 'api_key'
#      and an actual leaked credential.
#
#   2. DRIFT DETECTION — We don't just scan once. We track every NHI
#      over time and alert when permissions silently escalate.
#
#   3. FULLY AUTONOMOUS — Cloud Scheduler triggers hourly scans,
#      Pub/Sub fires alerts, Slack notifies the team. Zero human
#      intervention needed."


# ══════════════════════════════════════════════════════════════════
# SLIDE 6: FUTURE / Q&A (30 seconds)
# ══════════════════════════════════════════════════════════════════
#
# "Next steps:
#   - GitHub / Bitbucket integration (not just GitLab)
#   - Auto-rotation: when CRITICAL is detected, rotate the key
#     via GCP Secret Manager automatically
#   - Multi-repo fleet scanning across an entire org
#   - Integration with SIEM tools (Splunk, Datadog)
#
# Questions?"


# ══════════════════════════════════════════════════════════════════
# JUDGE Q&A — ANTICIPATED QUESTIONS
# ══════════════════════════════════════════════════════════════════
#
# Q: "How is this different from GitLab's built-in secret detection?"
# A: "GitLab detects secrets at commit time. We do continuous governance —
#    tracking drift, scoring context with AI, and alerting on escalation.
#    GitLab tells you 'there's a secret'. We tell you 'this secret's risk
#    just went from LOW to CRITICAL, here's why, and here's what to do.'"
#
# Q: "What happens if Gemini API is down?"
# A: "We have a heuristic fallback engine. Every pattern has a pre-scored
#    risk level. The system never stops — it degrades gracefully."
#
# Q: "How do you handle false positives?"
# A: "Gemini's contextual analysis dramatically reduces false positives.
#    A variable named 'password' in a comment is scored differently than
#    'password=hunter2' in a config file. The AI understands the difference."
#
# Q: "Can this scale to large repos?"
# A: "Yes — we scan files by extension (only code/config files),
#    use pagination for large repos, and Cloud Run auto-scales 0 to 3
#    instances. MongoDB handles millions of findings."
#
# Q: "Why MongoDB and not Firestore?"
# A: "MongoDB's flexible schema is perfect for NHI documents with varying
#    fields. The $push/$slice operator lets us track drift history without
#    unbounded document growth. But we could swap to Firestore easily."
