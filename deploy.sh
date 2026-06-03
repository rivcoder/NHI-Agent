#!/bin/bash
# agent_builder/deploy.sh
# One-shot GCP setup for NHI Governance Agent
# Usage: bash deploy.sh
# Prerequisites: gcloud CLI installed and authenticated

set -e

# ── Config — edit these ───────────────────────────────────────────────────────
PROJECT_ID="soy-sound-479918-k3"
REGION="us-central1"
SERVICE_ACCOUNT="nhi-agent-sa"
PUBSUB_TOPIC="nhi-critical-alerts"
SCHEDULER_JOB="nhi-hourly-scan"
CLOUD_RUN_SERVICE="nhi-alert-handler"
AGENT_BUILDER_AGENT="nhi-governance-agent"
GITLAB_REPO="https://gitlab.com/demo/acme-payments"

echo "🛡️  NHI Governance Agent — GCP Setup"
echo "======================================"

# ── 1. Set project ────────────────────────────────────────────────────────────
echo "[1/8] Setting GCP project..."
gcloud config set project "$PROJECT_ID"

# ── 2. Enable required APIs ───────────────────────────────────────────────────
echo "[2/8] Enabling APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  pubsub.googleapis.com \
  secretmanager.googleapis.com \
  aiplatform.googleapis.com \
  dialogflow.googleapis.com \
  logging.googleapis.com

# ── 3. Service account ────────────────────────────────────────────────────────
echo "[3/8] Creating service account..."
gcloud iam service-accounts create "$SERVICE_ACCOUNT" \
  --display-name="NHI Agent Service Account" || true

SA_EMAIL="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/pubsub.publisher"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"

# ── 4. Store secrets in Secret Manager ───────────────────────────────────────
echo "[4/8] Storing secrets..."
echo -n "$GEMINI_API_KEY" | gcloud secrets create gemini-api-key \
  --data-file=- --replication-policy="automatic" || true

echo -n "$MONGO_URI" | gcloud secrets create mongo-uri \
  --data-file=- --replication-policy="automatic" || true

echo -n "$GITLAB_TOKEN" | gcloud secrets create gitlab-token \
  --data-file=- --replication-policy="automatic" || true

# ── 5. Pub/Sub topic ──────────────────────────────────────────────────────────
echo "[5/8] Creating Pub/Sub topic..."
gcloud pubsub topics create "$PUBSUB_TOPIC" || true

# ── 6. Deploy Cloud Run alert handler ────────────────────────────────────────
echo "[6/8] Deploying Cloud Run alert handler..."
gcloud run deploy "$CLOUD_RUN_SERVICE" \
  --source=. \
  --region="$REGION" \
  --service-account="$SA_EMAIL" \
  --set-env-vars="PUBSUB_TOPIC=${PUBSUB_TOPIC}" \
  --set-secrets="MONGO_URI=mongo-uri:latest,GEMINI_API_KEY=gemini-api-key:latest,GITLAB_TOKEN=gitlab-token:latest" \
  --allow-unauthenticated \
  --min-instances=0 \
  --max-instances=3

CLOUD_RUN_URL=$(gcloud run services describe "$CLOUD_RUN_SERVICE" \
  --region="$REGION" --format="value(status.url)")

# ── 7. Pub/Sub push subscription → Cloud Run ─────────────────────────────────
echo "[7/8] Wiring Pub/Sub → Cloud Run..."
gcloud pubsub subscriptions create "${PUBSUB_TOPIC}-sub" \
  --topic="$PUBSUB_TOPIC" \
  --push-endpoint="${CLOUD_RUN_URL}/alert" \
  --push-auth-service-account="$SA_EMAIL" || true

# ── 8. Cloud Scheduler — hourly scan trigger ──────────────────────────────────
echo "[8/8] Creating hourly Cloud Scheduler job..."
gcloud scheduler jobs create http "$SCHEDULER_JOB" \
  --location="$REGION" \
  --schedule="0 * * * *" \
  --uri="${CLOUD_RUN_URL}/scan" \
  --http-method=POST \
  --message-body="{\"repo\": \"${GITLAB_REPO}\"}" \
  --headers="Content-Type=application/json" \
  --oidc-service-account-email="$SA_EMAIL" || true

echo ""
echo "✅ Setup complete!"
echo "   Cloud Run:      $CLOUD_RUN_URL"
echo "   Pub/Sub topic:  $PUBSUB_TOPIC"
echo "   Scheduler:      $SCHEDULER_JOB (every hour)"
echo ""
echo "Next: update PROJECT_ID and GITLAB_REPO at the top of this file."
