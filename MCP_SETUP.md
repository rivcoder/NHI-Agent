# 🔌 Model Context Protocol (MCP) Integration Guide

This guide explains how to host, deploy, and connect the official **GitLab** and **MongoDB** Model Context Protocol (MCP) servers to the **NHI Governance Agent** in Google Cloud Agent Builder.

---

## 🏗️ Architecture Overview

Google Cloud Agent Builder supports connecting directly to remote MCP servers. By deploying partner MCP servers on **Google Cloud Run**, our Gemini agent gains direct, standardized access to resources:

```
┌─────────────────────────────────┐
│   Google Cloud Agent Builder    │
│     (Gemini 2.5 Pro Agent)      │
└─────────────────────────────────┘
         │               │
         │ (MCP Proto)   │ (MCP Proto)
         ▼               ▼
┌────────────────┐┌────────────────┐
│   GitLab MCP   ││  MongoDB MCP   │
│  (Cloud Run)   ││  (Cloud Run)   │
└────────────────┘└────────────────┘
         │               │
         ▼               ▼
┌────────────────┐┌────────────────┐
│   GitLab API   ││ MongoDB Atlas  │
│  (Repositories)││ (Governance DB)│
└────────────────┘└────────────────┘
```

---

## 1. Hosting GitLab MCP on Google Cloud Run

The official GitLab MCP server enables Gemini to perform operations like fetching repo trees, reading files, and creating commit diffs.

### Step 1: Create the GitLab MCP Dockerfile
In a temporary directory, save the following `Dockerfile`:

```dockerfile
FROM node:20-slim
RUN npm install -g @modelcontextprotocol/server-gitlab
ENV GITLAB_PERSONAL_ACCESS_TOKEN=""
ENV GITLAB_API_URL="https://gitlab.com/api/v4"
EXPOSE 8080
CMD ["mcp-server-gitlab"]
```

### Step 2: Build and Deploy to Cloud Run
Run the following commands using the `gcloud` CLI:

```bash
# Build the container image in Artifact Registry
gcloud builds submit --tag gcr.io/YOUR_GCP_PROJECT/gitlab-mcp-server .

# Deploy to Cloud Run as a secure, authenticated service
gcloud run deploy gitlab-mcp-server \
  --image gcr.io/YOUR_GCP_PROJECT/gitlab-mcp-server \
  --region us-central1 \
  --set-env-vars="GITLAB_PERSONAL_ACCESS_TOKEN=your_glpat_token" \
  --no-allow-unauthenticated
```

---

## 2. Hosting MongoDB MCP on Google Cloud Run

The official MongoDB MCP server allows the agent to directly query and write drift data back to the database.

### Step 1: Create the MongoDB MCP Dockerfile
Save the following `Dockerfile`:

```dockerfile
FROM node:20-slim
RUN npm install -g @mongodb/mcp-server
ENV MONGODB_URI=""
EXPOSE 8080
CMD ["mongodb-mcp-server"]
```

### Step 2: Build and Deploy to Cloud Run
Run the following commands:

```bash
# Build the container image
gcloud builds submit --tag gcr.io/YOUR_GCP_PROJECT/mongodb-mcp-server .

# Deploy to Cloud Run
gcloud run deploy mongodb-mcp-server \
  --image gcr.io/YOUR_GCP_PROJECT/mongodb-mcp-server \
  --region us-central1 \
  --set-env-vars="MONGODB_URI=your_mongo_connection_string" \
  --no-allow-unauthenticated
```

---

## 3. Connecting MCP to Google Cloud Agent Builder

Once your MCP servers are running on Cloud Run, register them in your Agent Builder console.

### Step 1: Register the Tools
1. Navigate to **Google Cloud Console** > **Agent Builder** > **Tools**.
2. Click **Create Tool** and choose **Model Context Protocol (MCP)**.
3. Configure the **GitLab MCP Tool**:
   - **Name**: `gitlab_mcp`
   - **Description**: Exposes GitLab API tools to view repo files and branch structures.
   - **Server Address**: `https://gitlab-mcp-server-xxxxxx-uc.a.run.app/mcp`
   - **Authentication**: **Service Agent ID Token** (Google handles internal IAM auth automatically).
4. Configure the **MongoDB MCP Tool**:
   - **Name**: `mongodb_mcp`
   - **Description**: Exposes MongoDB API tools to query and write documents.
   - **Server Address**: `https://mongodb-mcp-server-xxxxxx-uc.a.run.app/mcp`
   - **Authentication**: **Service Agent ID Token**.

### Step 2: Assign Tools to your Agent
1. Open your Gemini Agent inside the **Agent Builder Console**.
2. Under the **Tools** section, check the boxes for `gitlab_mcp` and `mongodb_mcp`.
3. In your **System Instructions** (defined in `agent.yaml`), specify:
   > *"When asked to scan a repository, use `gitlab_mcp` to list repository files and inspect contents. To analyze historical records or write drift logs, use `mongodb_mcp`."*

---

## 🔒 Security & IAM

Using **Service Agent ID Token** authentication ensures that:
- Your MCP servers do not allow public internet access (`--no-allow-unauthenticated`).
- Only your authorized Google Agent Builder service account has permissions to invoke the tools.
- All credentials (like `GITLAB_PERSONAL_ACCESS_TOKEN` and `MONGODB_URI`) are encrypted and safely isolated in the Cloud Run service environment.
